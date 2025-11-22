from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.db import transaction
from django.contrib import messages
from django.db.models import Q
from django.forms import modelform_factory
from django.urls import reverse # Cần cho QR Code
from urllib.parse import quote # Cần cho mã hóa URL QR Code (FIX)
from django.contrib.auth import logout
from django.db.models import Sum, Count
from .models import StaffSchedule
from django.http import JsonResponse
from datetime import timedelta, date # Thêm date vào import
from .forms import StaffScheduleForm # Import Form mới
from django.contrib.auth.models import User, Group
from .forms import StaffUserForm

import pandas as pd
from io import BytesIO

from .models import Room, Guest, Reservation, GuestRequest, ServiceCharge, ServiceItem
from .forms import GuestForm, ReservationForm, ServiceChargeForm, ServiceItemForm

# Form sửa đổi nhanh thông tin Room
RoomEditForm = modelform_factory(
    Room,
    fields=('room_number', 'room_type', 'price_per_night','status'),
    labels={
        'room_number': 'Số Phòng',
        'room_type': 'Loại Phòng',
        'price_per_night': 'Giá/Đêm (VND)',
        'status': 'Trạng thái'
    }
)

# **********************************************
# 1. DASHBOARD CHÍNH VÀ LOGIC HIỂN THỊ PHÒNG
# **********************************************
@login_required
def dashboard(request):
    rooms = Room.objects.all().order_by('room_number')
    active_reservations = Reservation.objects.filter(
        status__in=['Confirmed', 'Occupied']
    ).select_related('guest')

    room_data = []
    CHECKIN_ALERT_WINDOW = timezone.timedelta(minutes=30)

    for room in rooms:
        current_res = active_reservations.filter(room=room).first()
        is_alerting = False

        if current_res:
            data = {
                'room': room,
                'reservation': current_res,
                'guest_name': current_res.guest.full_name,
                'is_alerting': False,
            }

            if current_res.status == 'Confirmed':
                room.status = 'Booked'
                time_until_checkin = current_res.check_in_date - timezone.now()

                if time_until_checkin < CHECKIN_ALERT_WINDOW and time_until_checkin > timezone.timedelta(0):
                    data['is_alerting'] = True

            elif current_res.status == 'Occupied':
                room.status = 'Occupied'

        else:
            room.status = 'Vacant'
            data = {'room': room, 'reservation': None, 'is_alerting': False}

        room_data.append(data)

    def sort_key(item):
        status = item['room'].status
        is_alerting = item['is_alerting']

        if status == 'Vacant': return 1
        if status == 'Booked':
            if is_alerting: return 2
            return 3
        if status == 'Occupied': return 4
        if status == 'Dirty': return 5
        return 6

    room_data.sort(key=sort_key)

    context = {
        'page_title': "Dashboard Quản lý Phòng",
        'room_data': room_data,
        'now': timezone.now()
    }
    return render(request, 'pms/dashboard.html', context)


# **********************************************
# 2. CHỨC NĂNG TẠO BOOKING/CHECK-IN
# **********************************************

@login_required
def create_booking(request, room_id):
    room = get_object_or_404(Room, id=room_id)

    if room.status == 'Occupied' or room.status == 'Booked':
        messages.error(request, f"Phòng {room.room_number} đang bận.")
        return redirect('dashboard')

    if request.method == 'POST':
        # 👇 QUAN TRỌNG: Thêm request.FILES để nhận ảnh
        guest_form = GuestForm(request.POST, request.FILES)
        reservation_form = ReservationForm(request.POST)

        if guest_form.is_valid() and reservation_form.is_valid():
            try:
                with transaction.atomic():
                    # ... (Giữ nguyên logic lưu Guest và Reservation) ...
                    guest_data = guest_form.cleaned_data
                    # Logic xử lý ảnh và lưu guest (giống code cũ của bạn)
                    guest_instance, created = Guest.objects.get_or_create(
                        id_number=guest_data['id_number'],
                        defaults=guest_data
                    )
                    if not created:
                        # Cập nhật thông tin nếu khách cũ
                        for key, value in guest_data.items():
                            if key != 'id_number': # Không sửa ID
                                setattr(guest_instance, key, value)
                        # Lưu file ảnh mới nếu có
                        if request.FILES.get('photo'):
                             guest_instance.photo = request.FILES['photo']
                        guest_instance.save()

                    reservation = reservation_form.save(commit=False)
                    reservation.room = room
                    reservation.guest = guest_instance
                    reservation.save()

                    # Cập nhật trạng thái phòng
                    if reservation.status == 'Occupied': room.status = 'Occupied'
                    elif reservation.status == 'Confirmed': room.status = 'Booked'
                    room.save()

                messages.success(request, "Tạo Booking thành công.")
                return redirect('dashboard')
            except Exception as e:
                messages.error(request, f"Lỗi: {e}")
    else:
        guest_form = GuestForm()
        reservation_form = ReservationForm(initial={'check_in_date': timezone.now()})

    context = {'room': room, 'guest_form': guest_form, 'reservation_form': reservation_form}
    return render(request, 'pms/booking_form.html', context)


# **********************************************
# 3. CHỨC NĂNG CHECK-IN CHÍNH THỨC
# **********************************************

@login_required
@transaction.atomic
def perform_check_in(request, reservation_id):
    reservation = get_object_or_404(Reservation, id=reservation_id)
    room = reservation.room

    if reservation.status != 'Confirmed':
        messages.error(request, "Booking này không ở trạng thái chờ Check-in.")
        return redirect('dashboard')

    reservation.status = 'Occupied'
    reservation.check_in_date = timezone.now()
    reservation.save()

    room.status = 'Occupied'
    room.save()

    messages.success(request, f"Phòng {room.room_number}: Check-in thành công cho khách {reservation.guest.full_name}.")

    return redirect('dashboard')


# **********************************************
# 4. TRANG HÓA ĐƠN VÀ XỬ LÝ CHECK-OUT
# **********************************************

def calculate_bill_details(reservation):
    """ Hàm tính toán chi tiết hóa đơn: tiền phòng và dịch vụ. """
    room = reservation.room
    check_out_time = timezone.now()

    duration = check_out_time - reservation.check_in_date
    num_nights = duration.days

    if duration.seconds >= 6 * 3600 or (num_nights == 0 and duration.seconds > 0):
        num_nights = num_nights + 1 if num_nights > 0 else 1

    if num_nights == 0: num_nights = 1

    total_room_cost = num_nights * room.price_per_night

    service_charges = ServiceCharge.objects.filter(reservation=reservation)
    total_service_cost = sum(charge.total_price for charge in service_charges)

    final_bill = total_room_cost + total_service_cost

    return {
        'num_nights': num_nights,
        'room_rate': room.price_per_night,
        'total_room_cost': total_room_cost,
        'service_charges': service_charges,
        'total_service_cost': total_service_cost,
        'final_bill': final_bill,
        'check_out_time': check_out_time,
    }

@login_required
def billing_details(request, reservation_id):
    reservation = get_object_or_404(Reservation, id=reservation_id)
    room = reservation.room

    if reservation.status != 'Occupied':
        messages.error(request, "Phòng này hiện không có khách cư trú để tính hóa đơn.")
        return redirect('dashboard')

    bill_details = calculate_bill_details(reservation)

    context = {
        'page_title': f"Hóa đơn & Thanh toán Phòng {room.room_number}",
        'reservation': reservation,
        'room': room,
        'guest': reservation.guest,
        'bill': bill_details,
    }
    return render(request, 'pms/billing_details.html', context)


@login_required
@transaction.atomic
def perform_check_out(request, reservation_id):
    if request.method != 'POST':
        return redirect('billing-details', reservation_id=reservation_id)

    reservation = get_object_or_404(Reservation, id=reservation_id)
    room = reservation.room

    if reservation.status != 'Occupied':
        messages.error(request, "Phòng này hiện không có khách cư trú.")
        return redirect('dashboard')

    bill_details = calculate_bill_details(reservation)
    final_bill = bill_details['final_bill']

    reservation.status = 'Completed'
    reservation.check_out_date = bill_details['check_out_time']
    reservation.save()

    room.status = 'Vacant'
    room.save()

    messages.success(request, f"Phòng {room.room_number}: Check-out thành công. Tổng tiền thanh toán: {final_bill:,} VND.")

    return redirect('dashboard')


# **********************************************
# 5. CHỨC NĂNG XUẤT FILE EXCEL ĐĂNG KÝ TẠM TRÚ
# **********************************************

@login_required
def export_temporary_registry(request):
    """
    Xuất file Excel chứa thông tin đăng ký tạm trú (dựa trên khách đang cư trú).
    """
    reservations = Reservation.objects.filter(status='Occupied').select_related('guest', 'room')

    data = []
    for res in reservations:
        guest = res.guest
        room = res.room

        check_out = res.check_out_date.strftime('%d/%m/%Y') if res.check_out_date else timezone.now().strftime('%d/%m/%Y (Hiện tại)')

        data.append({
            'STT': len(data) + 1,
            'Họ và Tên': guest.full_name,
            'Ngày sinh': guest.dob.strftime('%d/%m/%Y') if guest.dob else '',
            'Loại giấy tờ': guest.get_id_type_display(),
            'Mã số giấy tờ': guest.id_number,
            'Biển số xe': guest.license_plate if guest.license_plate else '',
            'Địa chỉ thường trú': guest.address,
            'Số điện thoại': guest.phone,
            'Thời gian cư trú': f"Từ {res.check_in_date.strftime('%d/%m/%Y')} đến {check_out}",
            'Phòng': room.room_number,
        })

    df = pd.DataFrame(data)

    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        sheet_name = 'DangKyTamTru'
        df.to_excel(writer, sheet_name=sheet_name, index=False)

        worksheet = writer.sheets[sheet_name]
        for idx, col in enumerate(df.columns):
            max_len = max(df[col].astype(str).map(len).max(), len(col)) + 2
            worksheet.column_dimensions[chr(65 + idx)].width = max_len

    output.seek(0)

    response = HttpResponse(
        output.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    filename = timezone.now().strftime('DangKyTamTru_%Y%m%d_%H%M.xlsx')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    messages.success(request, f"Đã xuất thành công {len(data)} hồ sơ đăng ký tạm trú.")
    return response

# **********************************************
# 6. YÊU CẦU KHÁCH HÀNG (QR CODE PORTAL)
# **********************************************

def guest_request_portal(request, room_id):
    room = get_object_or_404(Room, id=room_id)

    current_res = Reservation.objects.filter(room=room, status='Occupied').first()

    if not current_res:
        return render(request, 'pms/guest_inactive.html', {'room': room})

    if request.method == 'POST':
        content = request.POST.get('content')
        if content:
            GuestRequest.objects.create(
                room=room,
                reservation=current_res,
                content=content,
                status='New'
            )
            return render(request, 'pms/guest_success.html', {'room': room, 'message': 'Yêu cầu của quý khách đã được ghi nhận. Nhân viên sẽ xử lý sớm nhất.'})

    context = {
        'room': room,
        'guest_name': current_res.guest.full_name,
    }
    return render(request, 'pms/guest_request_form.html', context)


# **********************************************
# 7. QUẢN LÝ YÊU CẦU KHÁCH HÀNG (QR Code)
# **********************************************

@login_required
def manage_requests(request):
    """
    Trang quản lý các yêu cầu từ khách hàng (QR Code).
    """
    requests_list = GuestRequest.objects.filter(
        status__in=['New', 'Processing']
    ).select_related('room', 'reservation').order_by('created_at')

    context = {
        'page_title': 'Quản lý Yêu cầu Khách hàng (QR)',
        'requests_list': requests_list
    }
    return render(request, 'pms/manage_requests.html', context)

@login_required
@transaction.atomic
def complete_request(request, request_id):
    """
    API để nhân viên chuyển trạng thái yêu cầu thành Hoàn thành.
    """
    if request.method == 'POST':
        guest_request = get_object_or_404(GuestRequest, id=request_id)
        if guest_request.status != 'Completed':
            guest_request.status = 'Completed'
            guest_request.assigned_staff = request.user
            guest_request.save()
            messages.success(request, f"Đã hoàn thành yêu cầu từ phòng {guest_request.room.room_number}.")
        return redirect('manage-requests')
    return redirect('manage-requests')


# **********************************************
# 8. QUẢN LÝ DỊCH VỤ PHÒNG (SERVICE CHARGE)
# **********************************************

@login_required
def manage_room_services(request, reservation_id):
    reservation = get_object_or_404(Reservation, id=reservation_id)
    room = reservation.room

    if reservation.status != 'Occupied':
        messages.error(request, f"Phòng {room.room_number} hiện không có khách cư trú để thêm dịch vụ.")
        return redirect('dashboard')

    service_charges = ServiceCharge.objects.filter(reservation=reservation).order_by('-created_at')
    service_form = ServiceChargeForm()

    # 👇 THÊM DÒNG NÀY: Lấy danh sách thực đơn từ kho
    inventory_items = ServiceItem.objects.all().order_by('item_name')

    total_service_cost = sum(charge.total_price for charge in service_charges)

    context = {
        'page_title': f"Dịch vụ phòng {room.room_number}",
        'room': room,
        'reservation': reservation,
        'service_charges': service_charges,
        'service_form': service_form,
        'total_service_cost': total_service_cost,
        'inventory_items': inventory_items, # 👇 Đừng quên gửi biến này sang template
    }
    return render(request, 'pms/manage_room_services.html', context)


@login_required
def add_service_charge(request, reservation_id):
    reservation = get_object_or_404(Reservation, id=reservation_id)
    room = reservation.room

    if reservation.status != 'Occupied' or request.method != 'POST':
        messages.error(request, "Không thể thêm dịch vụ. Vui lòng kiểm tra trạng thái phòng.")
        return redirect('manage-room-services', reservation_id=reservation.id)

    form = ServiceChargeForm(request.POST)
    if form.is_valid():
        try:
            charge = form.save(commit=False)
            charge.reservation = reservation
            charge.save()
            messages.success(request, f"Đã thêm {charge.item_name} x {charge.quantity} vào phòng {room.room_number}.")
        except Exception as e:
            messages.error(request, f"Lỗi khi lưu: {e}")

    else:
        messages.error(request, "Dữ liệu không hợp lệ. Vui lòng kiểm tra lại Số lượng và Đơn giá.")

    return redirect('manage-room-services', reservation_id=reservation.id)

# **********************************************
# 9. LỊCH ĐẶT PHÒNG
# **********************************************

@login_required
def reservation_calendar(request):
    """
    Hiển thị danh sách tất cả các Booking (Confirmed) và Khách đang ở (Occupied).
    """
    reservations = Reservation.objects.filter(
        status__in=['Confirmed', 'Occupied']
    ).select_related('room', 'guest').order_by('check_in_date')

    context = {
        'page_title': 'Lịch Đặt phòng & Khách đang cư trú',
        'reservations': reservations
    }
    return render(request, 'pms/reservation_calendar.html', context)

# **********************************************
# 10. QUẢN LÝ THÔNG TIN PHÒNG
# **********************************************

@login_required
def manage_rooms(request):
    """
    Hiển thị danh sách tất cả các phòng để quản lý thông tin chi tiết (giá, loại).
    """
    rooms = Room.objects.all().order_by('room_number')
    context = {
        'page_title': 'Quản lý Cấu hình Phòng',
        'rooms': rooms,
    }
    return render(request, 'pms/manage_rooms.html', context)

@login_required
def room_edit(request, room_id):
    """
    Xử lý sửa đổi thông tin chi tiết (giá, loại phòng) của một phòng.
    """
    room = get_object_or_404(Room, id=room_id)

    if request.method == 'POST':
        form = RoomEditForm(request.POST, instance=room)
        if form.is_valid():
            form.save()
            messages.success(request, f"Đã cập nhật thông tin phòng {room.room_number} thành công.")
            return redirect('manage-rooms')
        else:
            messages.error(request, "Lỗi khi cập nhật thông tin phòng. Vui lòng kiểm tra lại dữ liệu.")
    else:
        form = RoomEditForm(instance=room)

    context = {
        'page_title': f"Sửa đổi Phòng {room.room_number}",
        'room': room,
        'form': form
    }
    return render(request, 'pms/room_edit_form.html', context)

# **********************************************
# 11. QUẢN LÝ DANH MỤC DỊCH VỤ
# **********************************************

@login_required
def manage_service_inventory(request):
    """ Hiển thị danh sách các mặt hàng/dịch vụ hiện có. """
    service_items = ServiceItem.objects.all().order_by('item_name')
    context = {
        'page_title': 'Quản lý Danh mục Dịch vụ',
        'service_items': service_items
    }
    return render(request, 'pms/service_inventory_management.html', context)

@login_required
def service_item_create(request):
    """ Tạo một mặt hàng dịch vụ mới. """
    if request.method == 'POST':
        form = ServiceItemForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, f"Đã tạo danh mục '{form.cleaned_data['item_name']}' thành công.")
            return redirect('manage-service-inventory')
    else:
        form = ServiceItemForm()

    context = {
        'page_title': 'Tạo Dịch vụ mới',
        'form': form,
        'action': 'Tạo'
    }
    return render(request, 'pms/service_item_form.html', context)

@login_required
def service_item_edit(request, item_id):
    """ Sửa thông tin một mặt hàng dịch vụ. """
    item = get_object_or_404(ServiceItem, id=item_id)

    if request.method == 'POST':
        form = ServiceItemForm(request.POST, instance=item)
        if form.is_valid():
            form.save()
            messages.success(request, f"Đã cập nhật danh mục '{item.item_name}' thành công.")
            return redirect('manage-service-inventory')
    else:
        form = ServiceItemForm(instance=item)

    context = {
        'page_title': f"Sửa Dịch vụ: {item.item_name}",
        'form': form,
        'action': 'Sửa'
    }
    return render(request, 'pms/service_item_form.html', context)

@login_required
@transaction.atomic
def service_item_delete(request, item_id):
    """ Xóa một mặt hàng dịch vụ. """
    item = get_object_or_404(ServiceItem, id=item_id)
    item_name = item.item_name

    if ServiceCharge.objects.filter(item_name=item_name).exists():
        messages.error(request, f"Không thể xóa '{item_name}' vì đã có giao dịch sử dụng dịch vụ này.")
        return redirect('manage-service-inventory')

    if request.method == 'POST':
        item.delete()
        messages.success(request, f"Đã xóa danh mục '{item_name}' thành công.")
        return redirect('manage-service-inventory')

    return redirect('manage-service-inventory')

# **********************************************
# 12. TẠO VÀ XEM QR CODE
# **********************************************

@login_required
def room_qr_code(request, room_id):
    """
    Hiển thị mã QR code cố định cho một phòng, liên kết đến Guest Request Portal.
    """
    room = get_object_or_404(Room, id=room_id)

    # 1. Xây dựng URL đích
    relative_url = reverse('guest-request-portal', args=[room.id])

    # 2. Xây dựng URL đầy đủ (Không cần encoding quá phức tạp nữa)
    full_request_url = request.build_absolute_uri(relative_url)

    # Chúng ta chỉ cần URL này để JavaScript tạo mã QR

    context = {
        'page_title': f"Mã QR Code Phòng {room.room_number}",
        'room': room,
        # Không còn qr_code_url, giờ chỉ dùng full_request_url trong template
        'full_request_url': full_request_url
    }
    return render(request, 'pms/room_qr_code.html', context)

@login_required
def manage_guests(request):
    """
    Hiển thị danh sách khách hàng đã lưu trữ, có chức năng tìm kiếm cơ bản.
    """
    search_query = request.GET.get('q', '')

    if search_query:
        guests = Guest.objects.filter(
            Q(full_name__icontains=search_query) |
            Q(id_number__icontains=search_query) |
            Q(phone__icontains=search_query)
        ).order_by('-created_at')
    else:
        guests = Guest.objects.all().order_by('-created_at')

    context = {
        'page_title': 'Quản lý Hồ sơ Khách hàng',
        'guests': guests,
        'search_query': search_query
    }
    return render(request, 'pms/manage_guests.html', context)

@login_required
def edit_guest(request, guest_id):
    guest = get_object_or_404(Guest, id=guest_id)

    if request.method == 'POST':
        # 👇 QUAN TRỌNG: Thêm request.FILES
        form = GuestForm(request.POST, request.FILES, instance=guest)
        if form.is_valid():
            form.save()
            messages.success(request, "Cập nhật thành công.")
            return redirect('manage-guests')
    else:
        form = GuestForm(instance=guest)

    context = {'page_title': f"Sửa hồ sơ: {guest.full_name}", 'form': form, 'guest': guest}
    return render(request, 'pms/guest_edit_form.html', context)

@login_required
@transaction.atomic
def delete_guest(request, guest_id):
    """
    Xóa hồ sơ khách hàng
    """
    guest = get_object_or_404(Guest, id=guest_id)

    if request.method == 'POST':
        # 1. Kiểm tra an toàn: Không xóa khách đang ở
        if Reservation.objects.filter(guest=guest, status='Occupied').exists():
            messages.error(request, f"Không thể xóa khách {guest.full_name} vì đang cư trú. Vui lòng Check-out trước.")
            return redirect('manage-guests')

        # 2. Thực hiện xóa
        guest_name = guest.full_name
        guest.delete()
        messages.success(request, f"Đã xóa khách hàng {guest_name} và lịch sử liên quan.")

    return redirect('manage-guests')


def custom_logout(request):
    """
    Hàm đăng xuất tùy chỉnh cho phép dùng GET request
    """
    logout(request)
    return redirect('login')

@login_required
@transaction.atomic
def delete_room(request, room_id):
    """
    Chức năng xóa phòng (Chỉ xóa khi phòng Trống hoặc Dơ)
    """
    room = get_object_or_404(Room, id=room_id)

    if request.method == 'POST':
        # 1. Kiểm tra an toàn
        if room.status in ['Occupied', 'Booked']:
            messages.error(request, f"Không thể xóa Phòng {room.room_number} vì đang có khách hoặc đã được đặt trước.")
            return redirect('room-edit', room_id=room.id)

        # 2. Thực hiện xóa
        room_number = room.room_number
        room.delete()
        messages.success(request, f"Đã xóa Phòng {room_number} thành công.")
        return redirect('manage-rooms')

    return redirect('manage-rooms')
@login_required
def room_create(request):
    """
    Chức năng thêm phòng mới
    """
    # Tạo Form riêng cho việc thêm mới (Bao gồm cả trường Hotel)
    RoomCreateForm = modelform_factory(
        Room,
        fields=('hotel', 'room_number', 'room_type', 'price_per_night', 'status'),
        labels={
            'hotel': 'Thuộc Khách sạn',
            'room_number': 'Số Phòng',
            'room_type': 'Loại Phòng',
            'price_per_night': 'Giá/Đêm (VND)',
            'status': 'Trạng thái ban đầu'
        }
    )

    if request.method == 'POST':
        form = RoomCreateForm(request.POST)
        if form.is_valid():
            room = form.save()
            messages.success(request, f"Đã thêm Phòng {room.room_number} thành công.")
            return redirect('manage-rooms')
        else:
            messages.error(request, "Lỗi khi thêm phòng. Vui lòng kiểm tra lại (Số phòng không được trùng).")
    else:
        form = RoomCreateForm()

    context = {
        'page_title': 'Thêm Phòng Mới',
        'form': form
    }
    return render(request, 'pms/room_add_form.html', context)

@login_required
def management_dashboard(request):
    today = timezone.now()
    current_month = today.month
    current_year = today.year

    # --- Phần thống kê (Giữ nguyên) ---
    occupied_rooms_count = Room.objects.filter(status='Occupied').count()

    guest_count_month = Reservation.objects.filter(
        check_in_date__month=current_month,
        check_in_date__year=current_year
    ).count()

    completed_reservations = Reservation.objects.filter(
        status='Completed',
        check_out_date__month=current_month,
        check_out_date__year=current_year
    )

    total_revenue = 0
    for res in completed_reservations:
        duration = res.check_out_date - res.check_in_date
        nights = duration.days if duration.days > 0 else 1
        room_revenue = nights * res.room.price_per_night
        service_revenue = ServiceCharge.objects.filter(reservation=res).aggregate(Sum('price'))['price__sum'] or 0
        total_revenue += (room_revenue + service_revenue)

    # --- PHẦN LỊCH LÀM VIỆC (LOGIC MỚI) ---
    # Tìm ngày Thứ 2 của tuần hiện tại
    start_of_week = today.date() - timedelta(days=today.weekday())
    week_dates = [start_of_week + timedelta(days=i) for i in range(7)] # Danh sách 7 ngày (T2 -> CN)

    # Cấu trúc dữ liệu cho bảng:
    # timetable = {
    #    'Morning': [ [Staff1, Staff2], [], [Staff3], ... ], (7 phần tử tương ứng 7 ngày)
    #    'Afternoon': ...
    # }

    shifts = ['Morning', 'Afternoon', 'Night']
    shift_labels = {'Morning': 'Ca Sáng', 'Afternoon': 'Ca Chiều', 'Night': 'Ca Đêm'}

    timetable = []

    for shift_code in shifts:
        row_data = {
            'label': shift_labels[shift_code],
            'days': []
        }
        for day in week_dates:
            # Lấy tất cả nhân viên làm việc trong ca này, ngày này
            staffs = StaffSchedule.objects.filter(date=day, shift=shift_code)
            row_data['days'].append(staffs)
        timetable.append(row_data)

    context = {
        'page_title': f'Báo cáo Quản trị - Tháng {current_month}',
        'occupied_count': occupied_rooms_count,
        'guest_month_count': guest_count_month,
        'revenue_month': total_revenue,
        'week_dates': week_dates, # Gửi danh sách ngày để làm tiêu đề cột
        'timetable': timetable,   # Dữ liệu bảng
        'today': today.date(),
    }
    return render(request, 'pms/management_dashboard.html', context)


# 2. THÊM HÀM MỚI: add_staff_schedule
@login_required
def add_staff_schedule(request):
    if request.method == 'POST':
        form = StaffScheduleForm(request.POST)
        if form.is_valid():
            # 1. Lấy đối tượng lịch nhưng CHƯA lưu vào DB
            schedule = form.save(commit=False)

            # 2. Lấy thông tin User người dùng đã chọn trong Dropdown
            user_obj = form.cleaned_data['selected_user']

            # 3. Tự động điền tên nhân viên (Lấy họ tên thật, nếu không có thì lấy username)
            if user_obj.first_name and user_obj.last_name:
                schedule.staff_name = f"{user_obj.last_name} {user_obj.first_name}"
            else:
                schedule.staff_name = user_obj.username

            # 4. Tự động điền chức vụ (Dựa trên quyền hạn)
            # Nếu là Admin -> Gán là 'Lễ tân' (Hoặc bạn có thể logic khác)
            # Vì model StaffSchedule đang dùng tiếng Anh (Reception/Guard...), ta gán giá trị tương ứng
            if user_obj.is_superuser:
                schedule.role = 'Reception' # Admin kiêm lễ tân
            else:
                schedule.role = 'Reception' # Nhân viên mặc định là lễ tân

            # 5. Lưu chính thức
            schedule.save()

            messages.success(request, f"Đã xếp lịch cho {schedule.staff_name} thành công.")
            return redirect('management-dashboard')
    else:
        form = StaffScheduleForm(initial={'date': timezone.now().date()})

    context = {
        'page_title': 'Thêm Lịch làm việc',
        'form': form
    }
    return render(request, 'pms/staff_schedule_form.html', context)

@login_required
def check_new_requests_count(request):
    """
    API trả về số lượng yêu cầu mới (status='New') để Web App báo tin (Ting ting)
    """
    count = GuestRequest.objects.filter(status='New').count()
    return JsonResponse({'count': count})

@login_required
def manage_staff(request):
    # Chỉ Admin/Superuser mới được vào trang này
    if not request.user.is_superuser:
        messages.error(request, "Bạn không có quyền truy cập trang Quản lý Nhân sự.")
        return redirect('dashboard')

    if request.method == 'POST':
        form = StaffUserForm(request.POST)
        if form.is_valid():
            user = form.save()

            # Phân quyền Group
            role = form.cleaned_data['role']
            if role == 'Manager':
                user.is_superuser = True # Set làm admin
                user.is_staff = True
            else:
                user.is_superuser = False # Nhân viên thường
                user.is_staff = False

            user.save()
            messages.success(request, f"Đã tạo tài khoản nhân viên {user.username} thành công.")
            return redirect('manage-staff')
    else:
        form = StaffUserForm()

    # Lấy danh sách nhân viên (trừ admin hệ thống ra cho đỡ rối nếu muốn)
    staff_list = User.objects.all().order_by('-date_joined')

    context = {
        'page_title': 'Quản lý Nhân sự & Phân quyền',
        'staff_list': staff_list,
        'form': form
    }
    return render(request, 'pms/manage_staff.html', context)

@login_required
def delete_staff(request, user_id):
    if not request.user.is_superuser:
        return redirect('dashboard')

    user = get_object_or_404(User, id=user_id)
    if user == request.user:
        messages.error(request, "Không thể tự xóa chính mình!")
    else:
        user.delete()
        messages.success(request, "Đã xóa nhân viên.")
    return redirect('manage-staff')
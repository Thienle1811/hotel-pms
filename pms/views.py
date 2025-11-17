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

import pandas as pd
from io import BytesIO

from .models import Room, Guest, Reservation, GuestRequest, ServiceCharge, ServiceItem
from .forms import GuestForm, ReservationForm, ServiceChargeForm, ServiceItemForm

# Form sửa đổi nhanh thông tin Room
RoomEditForm = modelform_factory(
    Room, 
    fields=('room_number', 'room_type', 'price_per_night'),
    labels={
        'room_number': 'Số Phòng', 
        'room_type': 'Loại Phòng', 
        'price_per_night': 'Giá/Đêm (VND)'
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
        messages.error(request, f"Phòng {room.room_number} đang có khách hoặc đã được đặt trước. Vui lòng chọn phòng khác.")
        return redirect('dashboard')
        
    if request.method == 'POST':
        guest_form = GuestForm(request.POST)
        reservation_form = ReservationForm(request.POST)

        if guest_form.is_valid() and reservation_form.is_valid():
            try:
                with transaction.atomic():
                    guest_data = guest_form.cleaned_data
                    guest_instance, created = Guest.objects.get_or_create(
                        id_number=guest_data['id_number'],
                        defaults=guest_data
                    )
                    if not created:
                        for key, value in guest_data.items():
                            if key != 'id_number':
                                setattr(guest_instance, key, value)
                        guest_instance.save()
                        
                    reservation = reservation_form.save(commit=False)
                    reservation.room = room
                    reservation.guest = guest_instance
                    
                    # KIỂM TRA TRÙNG PHÒNG THỦ CÔNG
                    checkout_end = reservation.check_out_date if reservation.check_out_date else (reservation.check_in_date + timezone.timedelta(days=1))
                    
                    conflicting_reservations = Reservation.objects.filter(
                        room=room, 
                        status__in=['Confirmed', 'Occupied']
                    ).exclude(pk=reservation.pk).filter(
                        Q(check_in_date__lt=checkout_end) & Q(check_out_date__gt=reservation.check_in_date)
                    )
                    
                    if conflicting_reservations.exists():
                        first_conflict = conflicting_reservations.first()
                        messages.error(request, f"Phòng {room.room_number} bị trùng với Booking của khách {first_conflict.guest.full_name} (Check-in: {first_conflict.check_in_date}).")
                        return redirect('create-booking', room_id=room.id)

                    reservation.save()
                    
                    if reservation.status == 'Occupied':
                        room.status = 'Occupied'
                    elif reservation.status == 'Confirmed':
                        room.status = 'Booked' 
                    
                    room.save()

                messages.success(request, f"Đã tạo Booking/Check-in thành công cho phòng {room.room_number}.")
                return redirect('dashboard')
                    
            except Exception as e:
                messages.error(request, f"Lỗi xảy ra trong quá trình lưu dữ liệu: {e}")
        else:
            messages.error(request, "Vui lòng kiểm tra lại thông tin. Có lỗi xảy ra trong form.")
            
    else:
        guest_form = GuestForm()
        initial_res_data = {
            'check_in_date': timezone.now().strftime('%Y-%m-%dT%H:%M'),
            'status': 'Occupied'
        }
        reservation_form = ReservationForm(initial=initial_res_data)

    context = {
        'room': room,
        'guest_form': guest_form,
        'reservation_form': reservation_form
    }
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

    room.status = 'Dirty'
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
    
    total_service_cost = sum(charge.total_price for charge in service_charges)
    
    context = {
        'page_title': f"Dịch vụ phòng {room.room_number}",
        'room': room,
        'reservation': reservation,
        'service_charges': service_charges,
        'service_form': service_form,
        'total_service_cost': total_service_cost
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
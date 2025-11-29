from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.db import transaction
from django.contrib import messages
from django.db.models import Q, Sum
from django.forms import modelform_factory, modelformset_factory
from django.urls import reverse
from django.contrib.auth import logout
from django.contrib.auth.models import User
from datetime import datetime, timedelta, date
import pandas as pd
from io import BytesIO

from .models import Room, Guest, Reservation, GuestRequest, ServiceCharge, ServiceItem, StaffSchedule
from .forms import GuestForm, ReservationForm, ServiceChargeForm, ServiceItemForm, StaffScheduleForm, StaffUserForm

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

@login_required
def dashboard(request):
    rooms = Room.objects.all().order_by('room_number')
    all_reservations = Reservation.objects.filter(
        status__in=['Confirmed', 'Occupied']
    ).select_related('guest').order_by('check_in_date')

    room_data = []
    CHECKIN_ALERT_WINDOW = timezone.timedelta(minutes=30)
    now = timezone.now()

    for room in rooms:
        current_res = all_reservations.filter(room=room, status='Occupied').first()
        if not current_res:
            current_res = all_reservations.filter(room=room, status='Confirmed').first()

        is_alerting = False
        display_status = room.status 

        if current_res:
            if current_res.status == 'Occupied':
                display_status = 'Occupied'
            elif current_res.status == 'Confirmed':
                if current_res.check_in_date.date() <= now.date():
                    display_status = 'Booked'
                    time_until_checkin = current_res.check_in_date - now
                    if time_until_checkin < CHECKIN_ALERT_WINDOW and time_until_checkin > timezone.timedelta(0):
                        is_alerting = True
                else:
                    pass 

        data = {
            'room': room,
            'reservation': current_res,
            'guest_name': current_res.guest.full_name if current_res else "",
            'is_alerting': is_alerting,
            'display_status': display_status 
        }
        room_data.append(data)

    def sort_key(item):
        status = item['display_status']
        if item['is_alerting']: return 0
        if status == 'Booked': return 1
        if status == 'Occupied': return 2
        if status == 'Dirty': return 3
        return 4 

    room_data.sort(key=sort_key)

    context = {
        'page_title': "Dashboard Quản lý Phòng",
        'room_data': room_data,
        'now': now
    }
    return render(request, 'pms/dashboard.html', context)

@login_required
def create_booking(request, room_id):
    room = get_object_or_404(Room, id=room_id)
    GuestFormSet = modelformset_factory(Guest, form=GuestForm, extra=0)

    if request.method == 'POST':
        main_id_number = request.POST.get('main-id_number')
        main_guest_instance = Guest.objects.filter(id_number=main_id_number).first() if main_id_number else None
        
        main_guest_form = GuestForm(request.POST, request.FILES, prefix='main', instance=main_guest_instance)
        reservation_form = ReservationForm(request.POST, prefix='res')
        guest_formset = GuestFormSet(request.POST, request.FILES, queryset=Guest.objects.none(), prefix='others')

        if main_guest_form.is_valid() and reservation_form.is_valid() and guest_formset.is_valid():
            new_check_in = reservation_form.cleaned_data.get('check_in_date')
            new_check_out = reservation_form.cleaned_data.get('check_out_date')

            if not new_check_out:
                if new_check_in:
                    new_check_out = new_check_in + timedelta(days=1)
                else:
                    messages.error(request, "Vui lòng nhập thời gian Check-in.")
                    context = {'room': room, 'main_guest_form': main_guest_form, 'reservation_form': reservation_form, 'guest_formset': guest_formset}
                    return render(request, 'pms/booking_form.html', context)

            overlapping_bookings = Reservation.objects.filter(
                room=room,
                status__in=['Confirmed', 'Occupied'],
                check_in_date__lt=new_check_out, 
                check_out_date__gt=new_check_in
            )

            if overlapping_bookings.exists():
                conflict_res = overlapping_bookings.first()
                conflict_out_str = conflict_res.check_out_date.strftime('%d/%m') if conflict_res.check_out_date else "??"
                msg = f"Lỗi: Phòng {room.room_number} đã kẹt lịch của khách {conflict_res.guest.full_name} ({conflict_res.check_in_date.strftime('%d/%m')} - {conflict_out_str})."
                messages.error(request, msg)
                context = {'room': room, 'main_guest_form': main_guest_form, 'reservation_form': reservation_form, 'guest_formset': guest_formset}
                return render(request, 'pms/booking_form.html', context)

            try:
                with transaction.atomic():
                    main_guest = main_guest_form.save()
                    
                    reservation = reservation_form.save(commit=False)
                    reservation.room = room
                    reservation.guest = main_guest
                    reservation.save()
                    reservation.occupants.add(main_guest)

                    for form in guest_formset:
                        if form.cleaned_data and form.cleaned_data.get('id_number'):
                            other_data = form.cleaned_data
                            other_guest, created = Guest.objects.get_or_create(
                                id_number=other_data['id_number'],
                                defaults=other_data
                            )
                            if not created:
                                for key, value in other_data.items():
                                    if key != 'id_number' and value: setattr(other_guest, key, value)
                                if form.cleaned_data.get('photo_front'): other_guest.photo_front = form.cleaned_data['photo_front']
                                if form.cleaned_data.get('photo_back'): other_guest.photo_back = form.cleaned_data['photo_back']
                                other_guest.save()
                            reservation.occupants.add(other_guest)

                    if reservation.check_in_date.date() <= timezone.now().date():
                        if room.status == 'Vacant': 
                             room.status = 'Booked'
                             room.save()

                messages.success(request, f"Tạo Booking thành công cho khách {main_guest.full_name}.")
                if 'next' in request.GET:
                    return redirect(request.GET['next'])
                return redirect('dashboard')

            except Exception as e:
                messages.error(request, f"Lỗi hệ thống: {e}")
        else:
             if not main_guest_form.is_valid(): messages.error(request, f"Lỗi khách chính: {main_guest_form.errors}")
             if not reservation_form.is_valid(): messages.error(request, f"Lỗi đặt phòng: {reservation_form.errors}")
             if not guest_formset.is_valid(): messages.error(request, f"Lỗi khách đi kèm: {guest_formset.errors}")

    else:
        main_guest_form = GuestForm(prefix='main')
        initial_date = timezone.now()
        check_in_param = request.GET.get('check_in')
        if check_in_param:
            try:
                date_obj = datetime.strptime(check_in_param, '%Y-%m-%d').date()
                initial_date = timezone.make_aware(datetime.combine(date_obj, datetime.now().time()))
            except ValueError:
                pass
        reservation_form = ReservationForm(initial={'check_in_date': initial_date}, prefix='res')
        guest_formset = GuestFormSet(queryset=Guest.objects.none(), prefix='others')

    context = {'room': room, 'main_guest_form': main_guest_form, 'reservation_form': reservation_form, 'guest_formset': guest_formset}
    return render(request, 'pms/booking_form.html', context)

@login_required
@transaction.atomic
def perform_check_in(request, reservation_id):
    reservation = get_object_or_404(Reservation, id=reservation_id)
    room = reservation.room

    if room.status == 'Occupied':
        current_occupant = Reservation.objects.filter(room=room, status='Occupied').first()
        if current_occupant and current_occupant.id != reservation.id:
            messages.error(request, f"KHÔNG THỂ CHECK-IN: Phòng {room.room_number} đang có khách ({current_occupant.guest.full_name}) đang ở. Vui lòng trả phòng cho khách cũ trước.")
            return redirect('dashboard')

    if reservation.status != 'Confirmed':
        messages.error(request, "Booking này không ở trạng thái chờ Check-in.")
        return redirect('dashboard')

    reservation.status = 'Occupied'
    if not reservation.check_in_date:
        reservation.check_in_date = timezone.now()
    reservation.save()

    room.status = 'Occupied'
    room.save()

    messages.success(request, f"Phòng {room.room_number}: Check-in thành công. Giờ vào: {reservation.check_in_date.strftime('%d/%m %H:%M')}")
    return redirect('dashboard')

@login_required
@transaction.atomic
def cancel_booking(request, reservation_id):
    reservation = get_object_or_404(Reservation, id=reservation_id)
    room = reservation.room

    if reservation.status != 'Confirmed':
        messages.error(request, "Chỉ có thể hủy các đơn đặt phòng chưa Check-in (Trạng thái 'Đã đặt').")
        return redirect('dashboard')

    if request.method == 'POST':
        reservation.status = 'Cancelled'
        reservation.save()
        room.status = 'Vacant'
        room.save()
        messages.success(request, f"Đã hủy đặt phòng của {reservation.guest.full_name}. Phòng {room.room_number} đã trống.")
        return redirect('dashboard')
    
    return redirect('dashboard')

def calculate_bill_details(reservation):
    room = reservation.room
    check_out_time = timezone.now()
    
    actual_check_in = reservation.check_in_date
    calculation_check_in = actual_check_in.replace(hour=12, minute=0, second=0, microsecond=0)

    duration = check_out_time - calculation_check_in
    num_nights = duration.days

    if duration.seconds > 6 * 3600:
        num_nights += 1
    
    if num_nights <= 0:
        num_nights = 1

    total_room_cost = num_nights * room.price_per_night

    service_charges = ServiceCharge.objects.filter(reservation=reservation)
    total_service_cost = sum(charge.total_price for charge in service_charges)

    # --- [MỚI] TÍNH TOÁN TRỪ CỌC ---
    grand_total = total_room_cost + total_service_cost
    deposit_amount = reservation.deposit
    final_bill = grand_total - deposit_amount
    # -------------------------------

    return {
        'num_nights': num_nights,
        'room_rate': room.price_per_night,
        'total_room_cost': total_room_cost,
        'service_charges': service_charges,
        'total_service_cost': total_service_cost,
        'grand_total': grand_total,
        'deposit': deposit_amount,
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

@login_required
def booking_management(request):
    """
    Trang Quản lý Đặt phòng dạng Lịch (V3: Fix lỗi hiển thị, thêm Logic Màu Cọc)
    """
    today = timezone.localdate() 
    
    start_date_str = request.GET.get('start_date')
    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        except ValueError:
            start_date = today
    else:
        start_date = today

    days_to_show = 30
    end_date = start_date + timedelta(days=days_to_show)
    date_list = [start_date + timedelta(days=i) for i in range(days_to_show)]
    rooms = Room.objects.all().order_by('room_number')

    range_start = timezone.make_aware(datetime.combine(start_date, datetime.min.time()))
    range_end = timezone.make_aware(datetime.combine(end_date, datetime.max.time()))

    reservations = Reservation.objects.filter(
        Q(status__in=['Confirmed', 'Occupied']),
        Q(check_in_date__lt=range_end), 
        (Q(check_out_date__gt=range_start) | Q(check_out_date__isnull=True))
    ).select_related('guest', 'room')

    booking_map = {}
    for res in reservations:
        if res.check_out_date:
            temp_out_dt = res.check_out_date
        else:
            if res.status == 'Occupied':
                tomorrow_dt = timezone.now() + timedelta(days=1)
                if res.check_in_date < tomorrow_dt: temp_out_dt = tomorrow_dt
                else: temp_out_dt = res.check_in_date + timedelta(days=1)
            else:
                temp_out_dt = res.check_in_date + timedelta(days=1)

        res_in_date = timezone.localtime(res.check_in_date).date()
        res_out_date = timezone.localtime(temp_out_dt).date()

        stay_start = max(start_date, res_in_date)
        stay_end = min(end_date, res_out_date)
        
        if res_in_date == res_out_date:
            if start_date <= res_in_date < end_date:
                booking_map[(res.room.id, res_in_date)] = res
        else:
            curr = stay_start
            while curr < stay_end:
                booking_map[(res.room.id, curr)] = res
                curr += timedelta(days=1)

    calendar_data = []
    for d in date_list:
        row = {
            'date': d,
            'is_weekend': d.weekday() >= 5,
            'is_today': d == today,
            'room_cells': []
        }
        for r in rooms:
            booking = booking_map.get((r.id, d))
            cell = {
                'room': r,
                'date_str': d.strftime('%Y-%m-%d'),
                'booking': booking,
                'status_class': ''
            }
            if booking:
                if booking.status == 'Occupied': 
                    cell['status_class'] = 'bg-danger text-white' # Đỏ: Đang ở
                elif booking.status == 'Confirmed': 
                    # --- [MỚI] LOGIC MÀU SẮC DỰA TRÊN TIỀN CỌC ---
                    if booking.deposit > 0:
                        cell['status_class'] = 'bg-primary text-white' # Xanh: Đã cọc
                    else:
                        cell['status_class'] = 'bg-warning text-dark'  # Vàng: Chưa cọc
                    # ---------------------------------------------
            
            row['room_cells'].append(cell)
        calendar_data.append(row)

    context = {
        'page_title': 'Lịch Đặt Phòng (30 Ngày)',
        'rooms': rooms,
        'calendar_data': calendar_data,
        'current_start_date': start_date,
        'prev_date': (start_date - timedelta(days=15)).strftime('%Y-%m-%d'),
        'next_date': (start_date + timedelta(days=15)).strftime('%Y-%m-%d'),
        'today_str': today.strftime('%Y-%m-%d'),
    }
    return render(request, 'pms/booking_management.html', context)

# ... (Giữ nguyên các hàm khác: export_temporary_registry, manage_requests...) ...
@login_required
def export_temporary_registry(request):
    reservations = Reservation.objects.filter(status='Occupied').prefetch_related('occupants', 'room')
    data = []
    stt = 1
    for res in reservations:
        room_name = res.room.room_number
        check_in = res.check_in_date.strftime('%d/%m/%Y')
        guests_to_export = res.occupants.all()
        if not guests_to_export: guests_to_export = [res.guest]
        for guest in guests_to_export:
            data.append({
                'STT': stt,
                'Họ và Tên': guest.full_name,
                'Ngày sinh': guest.dob.strftime('%d/%m/%Y') if guest.dob else '',
                'Loại giấy tờ': guest.get_id_type_display(),
                'Mã số giấy tờ': guest.id_number,
                'Biển số xe': guest.license_plate if guest.license_plate else '',
                'Địa chỉ thường trú': guest.address,
                'Số điện thoại': guest.phone,
                'Thời gian cư trú': f"Từ {check_in}",
                'Phòng': room_name,
            })
            stt += 1
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
    response = HttpResponse(output.read(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    filename = timezone.now().strftime('DangKyTamTru_%Y%m%d_%H%M.xlsx')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    messages.success(request, f"Đã xuất thành công {len(data)} hồ sơ đăng ký tạm trú.")
    return response

def guest_request_portal(request, room_id):
    room = get_object_or_404(Room, id=room_id)
    current_res = Reservation.objects.filter(room=room, status='Occupied').first()
    if not current_res: return render(request, 'pms/guest_inactive.html', {'room': room})
    if request.method == 'POST':
        content = request.POST.get('content')
        if content:
            GuestRequest.objects.create(room=room, reservation=current_res, content=content, status='New')
            return render(request, 'pms/guest_success.html', {'room': room, 'message': 'Yêu cầu của quý khách đã được ghi nhận. Nhân viên sẽ xử lý sớm nhất.'})
    context = {'room': room, 'guest_name': current_res.guest.full_name}
    return render(request, 'pms/guest_request_form.html', context)

@login_required
def manage_requests(request):
    requests_list = GuestRequest.objects.filter(status__in=['New', 'Processing']).select_related('room', 'reservation').order_by('created_at')
    context = {'page_title': 'Quản lý Yêu cầu Khách hàng (QR)', 'requests_list': requests_list}
    return render(request, 'pms/manage_requests.html', context)

@login_required
@transaction.atomic
def complete_request(request, request_id):
    if request.method == 'POST':
        guest_request = get_object_or_404(GuestRequest, id=request_id)
        if guest_request.status != 'Completed':
            guest_request.status = 'Completed'
            guest_request.assigned_staff = request.user
            guest_request.save()
            messages.success(request, f"Đã hoàn thành yêu cầu từ phòng {guest_request.room.room_number}.")
    return redirect('manage-requests')

@login_required
def manage_room_services(request, reservation_id):
    reservation = get_object_or_404(Reservation, id=reservation_id)
    room = reservation.room
    if reservation.status != 'Occupied':
        messages.error(request, f"Phòng {room.room_number} hiện không có khách cư trú để thêm dịch vụ.")
        return redirect('dashboard')
    service_charges = ServiceCharge.objects.filter(reservation=reservation).order_by('-created_at')
    service_form = ServiceChargeForm()
    inventory_items = ServiceItem.objects.all().order_by('item_name')
    total_service_cost = sum(charge.total_price for charge in service_charges)
    context = {
        'page_title': f"Dịch vụ phòng {room.room_number}",
        'room': room,
        'reservation': reservation,
        'service_charges': service_charges,
        'service_form': service_form,
        'total_service_cost': total_service_cost,
        'inventory_items': inventory_items, 
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
        messages.error(request, "Dữ liệu không hợp lệ.")
    return redirect('manage-room-services', reservation_id=reservation.id)

@login_required
def reservation_calendar(request):
    reservations = Reservation.objects.filter(status__in=['Confirmed', 'Occupied']).select_related('room', 'guest').order_by('check_in_date')
    context = {'page_title': 'Lịch Đặt phòng & Khách đang cư trú', 'reservations': reservations}
    return render(request, 'pms/reservation_calendar.html', context)

@login_required
def manage_rooms(request):
    rooms = Room.objects.all().order_by('room_number')
    context = {'page_title': 'Quản lý Cấu hình Phòng', 'rooms': rooms}
    return render(request, 'pms/manage_rooms.html', context)

@login_required
def room_edit(request, room_id):
    room = get_object_or_404(Room, id=room_id)
    if request.method == 'POST':
        form = RoomEditForm(request.POST, instance=room)
        if form.is_valid():
            form.save()
            messages.success(request, f"Đã cập nhật thông tin phòng {room.room_number} thành công.")
            return redirect('manage-rooms')
    else:
        form = RoomEditForm(instance=room)
    context = {'page_title': f"Sửa đổi Phòng {room.room_number}", 'room': room, 'form': form}
    return render(request, 'pms/room_edit_form.html', context)

@login_required
def manage_service_inventory(request):
    service_items = ServiceItem.objects.all().order_by('item_name')
    context = {'page_title': 'Quản lý Danh mục Dịch vụ', 'service_items': service_items}
    return render(request, 'pms/service_inventory_management.html', context)

@login_required
def service_item_create(request):
    if request.method == 'POST':
        form = ServiceItemForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, f"Đã tạo danh mục '{form.cleaned_data['item_name']}' thành công.")
            return redirect('manage-service-inventory')
    else:
        form = ServiceItemForm()
    context = {'page_title': 'Tạo Dịch vụ mới', 'form': form, 'action': 'Tạo'}
    return render(request, 'pms/service_item_form.html', context)

@login_required
def service_item_edit(request, item_id):
    item = get_object_or_404(ServiceItem, id=item_id)
    if request.method == 'POST':
        form = ServiceItemForm(request.POST, instance=item)
        if form.is_valid():
            form.save()
            messages.success(request, f"Đã cập nhật danh mục '{item.item_name}' thành công.")
            return redirect('manage-service-inventory')
    else:
        form = ServiceItemForm(instance=item)
    context = {'page_title': f"Sửa Dịch vụ: {item.item_name}", 'form': form, 'action': 'Sửa'}
    return render(request, 'pms/service_item_form.html', context)

@login_required
@transaction.atomic
def service_item_delete(request, item_id):
    item = get_object_or_404(ServiceItem, id=item_id)
    item_name = item.item_name
    if ServiceCharge.objects.filter(item_name=item_name).exists():
        messages.error(request, f"Không thể xóa '{item_name}' vì đã có giao dịch sử dụng dịch vụ này.")
        return redirect('manage-service-inventory')
    if request.method == 'POST':
        item.delete()
        messages.success(request, f"Đã xóa danh mục '{item_name}' thành công.")
    return redirect('manage-service-inventory')

@login_required
def room_qr_code(request, room_id):
    room = get_object_or_404(Room, id=room_id)
    relative_url = reverse('guest-request-portal', args=[room.id])
    full_request_url = request.build_absolute_uri(relative_url)
    context = {'page_title': f"Mã QR Code Phòng {room.room_number}", 'room': room, 'full_request_url': full_request_url}
    return render(request, 'pms/room_qr_code.html', context)

@login_required
def manage_guests(request):
    search_query = request.GET.get('q', '')
    if search_query:
        guests = Guest.objects.filter(Q(full_name__icontains=search_query) | Q(id_number__icontains=search_query) | Q(phone__icontains=search_query)).order_by('-created_at')
    else:
        guests = Guest.objects.all().order_by('-created_at')
    context = {'page_title': 'Quản lý Hồ sơ Khách hàng', 'guests': guests, 'search_query': search_query}
    return render(request, 'pms/manage_guests.html', context)

@login_required
def edit_guest(request, guest_id):
    guest = get_object_or_404(Guest, id=guest_id)
    if request.method == 'POST':
        form = GuestForm(request.POST, request.FILES, instance=guest)
        if form.is_valid():
            form.save()
            messages.success(request, "Cập nhật thành công.")
            return redirect('manage-guests')
        else: messages.error(request, f"Lỗi cập nhật: {form.errors}")
    else:
        form = GuestForm(instance=guest)
    context = {'page_title': f"Sửa hồ sơ: {guest.full_name}", 'form': form, 'guest': guest}
    return render(request, 'pms/guest_edit_form.html', context)

@login_required
@transaction.atomic
def delete_guest(request, guest_id):
    guest = get_object_or_404(Guest, id=guest_id)
    if request.method == 'POST':
        if Reservation.objects.filter(guest=guest, status='Occupied').exists():
            messages.error(request, f"Không thể xóa khách {guest.full_name} vì đang cư trú. Vui lòng Check-out trước.")
            return redirect('manage-guests')
        guest_name = guest.full_name
        guest.delete()
        messages.success(request, f"Đã xóa khách hàng {guest_name} và lịch sử liên quan.")
    return redirect('manage-guests')

def custom_logout(request):
    logout(request)
    return redirect('login')

@login_required
@transaction.atomic
def delete_room(request, room_id):
    room = get_object_or_404(Room, id=room_id)
    if request.method == 'POST':
        if room.status in ['Occupied', 'Booked']:
            messages.error(request, f"Không thể xóa Phòng {room.room_number} vì đang có khách hoặc đã được đặt trước.")
            return redirect('room-edit', room_id=room.id)
        room_number = room.room_number
        room.delete()
        messages.success(request, f"Đã xóa Phòng {room_number} thành công.")
    return redirect('manage-rooms')

@login_required
def room_create(request):
    RoomCreateForm = modelform_factory(
        Room,
        fields=('hotel', 'room_number', 'room_type', 'price_per_night', 'status'),
        labels={'hotel': 'Thuộc Khách sạn', 'room_number': 'Số Phòng', 'room_type': 'Loại Phòng', 'price_per_night': 'Giá/Đêm (VND)', 'status': 'Trạng thái ban đầu'}
    )
    if request.method == 'POST':
        form = RoomCreateForm(request.POST)
        if form.is_valid():
            room = form.save()
            messages.success(request, f"Đã thêm Phòng {room.room_number} thành công.")
            return redirect('manage-rooms')
        else: messages.error(request, "Lỗi khi thêm phòng. Vui lòng kiểm tra lại (Số phòng không được trùng).")
    else:
        form = RoomCreateForm()
    context = {'page_title': 'Thêm Phòng Mới', 'form': form}
    return render(request, 'pms/room_add_form.html', context)

@login_required
def management_dashboard(request):
    today = timezone.now()
    current_month = today.month
    current_year = today.year
    occupied_rooms_count = Room.objects.filter(status='Occupied').count()
    guest_count_month = Reservation.objects.filter(check_in_date__month=current_month, check_in_date__year=current_year).count()
    completed_reservations = Reservation.objects.filter(status='Completed', check_out_date__month=current_month, check_out_date__year=current_year)
    total_revenue = 0
    for res in completed_reservations:
        duration = res.check_out_date - res.check_in_date
        nights = duration.days if duration.days > 0 else 1
        room_revenue = nights * res.room.price_per_night
        service_revenue = ServiceCharge.objects.filter(reservation=res).aggregate(Sum('price'))['price__sum'] or 0
        total_revenue += (room_revenue + service_revenue)
    start_of_week = today.date() - timedelta(days=today.weekday())
    week_dates = [start_of_week + timedelta(days=i) for i in range(7)]
    shifts = ['Morning', 'Afternoon', 'Night']
    shift_labels = {'Morning': 'Ca Sáng', 'Afternoon': 'Ca Chiều', 'Night': 'Ca Đêm'}
    timetable = []
    for shift_code in shifts:
        row_data = {'label': shift_labels[shift_code], 'days': []}
        for day in week_dates:
            staffs = StaffSchedule.objects.filter(date=day, shift=shift_code)
            row_data['days'].append(staffs)
        timetable.append(row_data)
    context = {'page_title': f'Báo cáo Quản trị - Tháng {current_month}', 'occupied_count': occupied_rooms_count, 'guest_month_count': guest_count_month, 'revenue_month': total_revenue, 'week_dates': week_dates, 'timetable': timetable, 'today': today.date()}
    return render(request, 'pms/management_dashboard.html', context)

@login_required
def add_staff_schedule(request):
    if request.method == 'POST':
        form = StaffScheduleForm(request.POST)
        if form.is_valid():
            schedule = form.save(commit=False)
            user_obj = form.cleaned_data['selected_user']
            if user_obj.first_name and user_obj.last_name: schedule.staff_name = f"{user_obj.last_name} {user_obj.first_name}"
            else: schedule.staff_name = user_obj.username
            if user_obj.is_superuser: schedule.role = 'Reception'
            else: schedule.role = 'Reception'
            schedule.save()
            messages.success(request, f"Đã xếp lịch cho {schedule.staff_name} thành công.")
            return redirect('management-dashboard')
        else: messages.error(request, "Lỗi nhập liệu.")
    else:
        form = StaffScheduleForm(initial={'date': timezone.now().date()})
    context = {'page_title': 'Thêm Lịch làm việc', 'form': form}
    return render(request, 'pms/staff_schedule_form.html', context)

@login_required
def check_new_requests_count(request):
    count = GuestRequest.objects.filter(status='New').count()
    return JsonResponse({'count': count})

@login_required
def manage_staff(request):
    if not request.user.is_superuser:
        messages.error(request, "Bạn không có quyền truy cập trang Quản lý Nhân sự.")
        return redirect('dashboard')
    if request.method == 'POST':
        form = StaffUserForm(request.POST)
        if form.is_valid():
            user = form.save()
            role = form.cleaned_data['role']
            if role == 'Manager': user.is_superuser = True; user.is_staff = True
            else: user.is_superuser = False; user.is_staff = False
            user.save()
            messages.success(request, f"Đã tạo tài khoản nhân viên {user.username} thành công.")
            return redirect('manage-staff')
        else: messages.error(request, f"Lỗi tạo nhân viên: {form.errors}")
    else: form = StaffUserForm()
    staff_list = User.objects.all().order_by('-date_joined')
    context = {'page_title': 'Quản lý Nhân sự & Phân quyền', 'staff_list': staff_list, 'form': form}
    return render(request, 'pms/manage_staff.html', context)

@login_required
def delete_staff(request, user_id):
    if not request.user.is_superuser: return redirect('dashboard')
    user = get_object_or_404(User, id=user_id)
    if user == request.user: messages.error(request, "Không thể tự xóa chính mình!")
    else: user.delete(); messages.success(request, "Đã xóa nhân viên.")
    return redirect('manage-staff')

# pms/views.py

@login_required
def dashboard(request):
    rooms = Room.objects.all().order_by('room_number')
    all_reservations = Reservation.objects.filter(
        status__in=['Confirmed', 'Occupied']
    ).select_related('guest').order_by('check_in_date')

    room_data = []
    CHECKIN_ALERT_WINDOW = timezone.timedelta(minutes=30)
    now = timezone.now()

    for room in rooms:
        current_res = all_reservations.filter(room=room, status='Occupied').first()
        if not current_res:
            current_res = all_reservations.filter(room=room, status='Confirmed').first()

        is_alerting = False
        display_status = room.status 

        if current_res:
            if current_res.status == 'Occupied':
                display_status = 'Occupied'
            elif current_res.status == 'Confirmed':
                if current_res.check_in_date.date() <= now.date():
                    display_status = 'Booked'
                    time_until_checkin = current_res.check_in_date - now
                    if time_until_checkin < CHECKIN_ALERT_WINDOW and time_until_checkin > timezone.timedelta(0):
                        is_alerting = True
                else:
                    pass 
        else:
            # === ĐOẠN FIX LỖI "NO REVERSE MATCH" ===
            # Nếu không tìm thấy Reservation nào nhưng trạng thái phòng đang là Booked hoặc Occupied
            # thì reset về Vacant để tránh lỗi template (Ghost booking)
            if display_status in ['Booked', 'Occupied']:
                display_status = 'Vacant'
            # =======================================

        data = {
            'room': room,
            'reservation': current_res,
            'guest_name': current_res.guest.full_name if current_res else "",
            'is_alerting': is_alerting,
            'display_status': display_status 
        }
        room_data.append(data)

    def sort_key(item):
        status = item['display_status']
        if item['is_alerting']: return 0
        if status == 'Booked': return 1
        if status == 'Occupied': return 2
        if status == 'Dirty': return 3
        return 4 

    room_data.sort(key=sort_key)

    context = {
        'page_title': "Dashboard Quản lý Phòng",
        'room_data': room_data,
        'now': now
    }
    
    # === QUAN TRỌNG: PHẢI CÓ DÒNG RETURN NÀY Ở CẤP ĐỘ NGOÀI CÙNG ===
    return render(request, 'pms/dashboard.html', context)
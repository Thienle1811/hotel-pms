from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
# 👇 THÊM DÒNG QUAN TRỌNG NÀY
from rest_framework.authentication import TokenAuthentication 
from django.shortcuts import get_object_or_404
from django.utils import timezone
from datetime import timedelta 
from django.db.models import Q
from django.db import transaction

from .models import Room, Guest, Reservation, ServiceItem, GuestRequest, ServiceCharge
from .serializers import (
    RoomSerializer, GuestSerializer, ReservationSerializer, 
    ServiceItemSerializer, GuestRequestSerializer
)

# --- 1. API cho Dashboard (Danh sách phòng & Trạng thái) ---
class DashboardAPIView(APIView):
    # 👇 BẮT BUỘC PHẢI CÓ DÒNG NÀY ĐỂ NHẬN TOKEN TỪ APP
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated] 

    def get(self, request):
        rooms = Room.objects.all().order_by('room_number')
        room_data = []
        
        active_reservations = Reservation.objects.filter(
            status__in=['Confirmed', 'Occupied']
        ).select_related('guest')

        CHECKIN_ALERT_WINDOW = timedelta(minutes=30) 

        for room in rooms:
            current_res = active_reservations.filter(room=room).first()
            is_alerting = False
            guest_name = ""
            reservation_id = None
            
            status_display = room.get_status_display()

            if current_res:
                guest_name = current_res.guest.full_name
                reservation_id = current_res.id
                
                if current_res.status == 'Confirmed':
                    status_display = "Đã đặt (Vàng)"
                    time_until_checkin = current_res.check_in_date - timezone.now()
                    if time_until_checkin < CHECKIN_ALERT_WINDOW and time_until_checkin > timedelta(0):
                        is_alerting = True
                
                elif current_res.status == 'Occupied':
                     status_display = "Đang có khách (Đỏ)"
            
            room_data.append({
                'room_id': room.id,
                'room_number': room.room_number,
                'room_type': room.room_type,
                'price': room.price_per_night,
                'status': room.status,           
                'status_display': status_display,
                'guest_name': guest_name,       
                'reservation_id': reservation_id,
                'is_alerting': is_alerting
            })
        
        return Response(room_data)

# --- 2. API Chi tiết 1 Phòng ---
class RoomDetailAPIView(APIView):
    authentication_classes = [TokenAuthentication] # <--- Thêm dòng này
    permission_classes = [IsAuthenticated]

    def get(self, request, room_id):
        room = get_object_or_404(Room, id=room_id)
        
        current_res = Reservation.objects.filter(
            room=room, 
            status__in=['Confirmed', 'Occupied']
        ).select_related('guest').first()

        serializer = RoomSerializer(room)
        data = serializer.data
        
        if current_res:
            res_serializer = ReservationSerializer(current_res)
            data['current_reservation'] = res_serializer.data
        else:
            data['current_reservation'] = None
            
        return Response(data)

# --- 3. ViewSets ---
class ServiceItemViewSet(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication] # <--- Thêm dòng này
    # permission_classes = [IsAuthenticated] 
    queryset = ServiceItem.objects.all()
    serializer_class = ServiceItemSerializer

class GuestRequestViewSet(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication] # <--- Thêm dòng này
    queryset = GuestRequest.objects.all().order_by('-created_at')
    serializer_class = GuestRequestSerializer


from .models import ServiceCharge # Nhớ đảm bảo đã import ServiceCharge

class AddServiceChargeAPIView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        # 1. Lấy dữ liệu từ App gửi lên
        reservation_id = request.data.get('reservation_id')
        item_id = request.data.get('item_id')
        quantity = int(request.data.get('quantity', 1))

        # 2. Kiểm tra dữ liệu
        reservation = get_object_or_404(Reservation, id=reservation_id)
        service_item = get_object_or_404(ServiceItem, id=item_id)

        # 3. Tạo bản ghi phí dịch vụ
        charge = ServiceCharge.objects.create(
            reservation=reservation,
            item_name=service_item.item_name,
            price=service_item.price, # Lấy giá hiện tại của dịch vụ
            quantity=quantity
        )

        # 4. Trả về kết quả thành công
        return Response({
            "message": f"Đã thêm {quantity} {service_item.item_name}",
            "charge": {
                "item_name": charge.item_name,
                "total_price": charge.total_price
            }
        }, status=status.HTTP_201_CREATED)
    
class CheckoutAPIView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, reservation_id):
        """API xem trước hóa đơn (Tạm tính)"""
        reservation = get_object_or_404(Reservation, id=reservation_id)
        room = reservation.room

        # 1. Logic tính tiền phòng (Giống hệt logic trên Web)
        check_out_time = timezone.now()
        duration = check_out_time - reservation.check_in_date
        num_nights = duration.days
        
        # Quy tắc làm tròn đêm (Quá 6 tiếng hoặc ở trong ngày tính 1 đêm)
        if duration.seconds >= 6 * 3600 or (num_nights == 0 and duration.seconds > 0):
            num_nights += 1
        if num_nights == 0: num_nights = 1 # Tối thiểu 1 đêm

        total_room_cost = num_nights * room.price_per_night

        # 2. Logic tính tiền dịch vụ
        service_charges = ServiceCharge.objects.filter(reservation=reservation)
        total_service_cost = sum(charge.total_price for charge in service_charges)
        
        # 3. Tổng cộng
        final_bill = total_room_cost + total_service_cost

        return Response({
            "room_number": room.room_number,
            "guest_name": reservation.guest.full_name,
            "check_in": reservation.check_in_date,
            "check_out_now": check_out_time,
            "num_nights": num_nights,
            "price_per_night": room.price_per_night,
            "total_room_cost": total_room_cost,
            "total_service_cost": total_service_cost,
            "final_bill": final_bill
        })

    def post(self, request, reservation_id):
        """API xác nhận Check-out"""
        reservation = get_object_or_404(Reservation, id=reservation_id)
        room = reservation.room

        if reservation.status != 'Occupied':
             return Response({"error": "Phòng này không có khách hoặc đã trả phòng."}, status=400)

        # Cập nhật Booking
        reservation.status = 'Completed'
        reservation.check_out_date = timezone.now()
        reservation.save()

        # Cập nhật Phòng -> Chuyển sang 'Dirty' để dọn dẹp
        room.status = 'Vacant' 
        room.save()

        return Response({"message": f"Đã trả phòng {room.room_number} thành công. Tổng thu: {request.data.get('final_bill', 0)}"})

class CheckinAPIView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, reservation_id):
        # 1. Lấy thông tin Booking
        reservation = get_object_or_404(Reservation, id=reservation_id)
        room = reservation.room

        # 2. Kiểm tra trạng thái
        if reservation.status != 'Confirmed':
            return Response({"error": "Booking này không ở trạng thái chờ Check-in."}, status=400)
        
        # 3. Thực hiện Check-in (Cập nhật trạng thái)
        reservation.status = 'Occupied'
        reservation.check_in_date = timezone.now()
        reservation.save()

        # Cập nhật trạng thái phòng
        room.status = 'Occupied'
        room.save()

        return Response({"message": f"Check-in thành công cho phòng {room.room_number}"})
    
class WalkInCheckinAPIView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, room_id):
        room = get_object_or_404(Room, id=room_id)
        
        # Cho phép check-in nếu phòng Trống hoặc Dơ (phòng trường hợp chưa kịp dọn trên hệ thống)
        if room.status != 'Vacant' and room.status != 'Dirty':
            return Response({"error": "Phòng này đang có khách."}, status=400)

        full_name = request.data.get('full_name')
        id_number = request.data.get('id_number')
        phone = request.data.get('phone', '')
        dob = request.data.get('dob')
        address = request.data.get('address', '')
        license_plate = request.data.get('license_plate', '')

        if not full_name or not id_number:
            return Response({"error": "Thiếu tên hoặc số giấy tờ."}, status=400)

        try:
            with transaction.atomic():
                guest, created = Guest.objects.get_or_create(
                    id_number=id_number,
                    defaults={
                        'full_name': full_name,
                        'phone': phone,
                        'dob': dob if dob else None,
                        'address': address if address else 'Khách vãng lai', # <--- LƯU ĐỊA CHỈ
                        'license_plate': license_plate,
                        'id_type': 'CCCD'
                    }
                )
                
                if not created:
                    guest.full_name = full_name
                    guest.phone = phone
                    if dob: guest.dob = dob
                    if address: guest.address = address # <--- Cập nhật địa chỉ nếu có
                    guest.save()

                Reservation.objects.create(
                    room=room,
                    guest=guest,
                    check_in_date=timezone.now(),
                    status='Occupied',
                    note='Check-in tại quầy (App)'
                )

                room.status = 'Occupied'
                room.save()

            return Response({"message": f"Check-in thành công phòng {room.room_number}"})
            
        except Exception as e:
            return Response({"error": str(e)}, status=500)
    
    
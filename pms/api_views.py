from rest_framework import viewsets, status, filters
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import TokenAuthentication 
from django.shortcuts import get_object_or_404
from django.utils import timezone
from datetime import timedelta 
from django.db.models import Q, Sum
from django.db import transaction

from .models import Room, Guest, Reservation, ServiceItem, GuestRequest, ServiceCharge, StaffSchedule
from .serializers import (
    RoomSerializer, GuestSerializer, ReservationSerializer, 
    ServiceItemSerializer, GuestRequestSerializer,
    StaffScheduleSerializer, CreateReservationSerializer
)

# --- 1. API cho Dashboard (Danh sách phòng & Trạng thái) ---
class DashboardAPIView(APIView):
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
    authentication_classes = [TokenAuthentication]
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

# --- 3. Các ViewSets cơ bản ---
class ServiceItemViewSet(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated] 
    queryset = ServiceItem.objects.all()
    serializer_class = ServiceItemSerializer

class GuestRequestViewSet(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]
    queryset = GuestRequest.objects.all().order_by('-created_at')
    serializer_class = GuestRequestSerializer

# --- 4. API Thêm Dịch Vụ ---
class AddServiceChargeAPIView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        reservation_id = request.data.get('reservation_id')
        item_id = request.data.get('item_id')
        quantity = int(request.data.get('quantity', 1))

        reservation = get_object_or_404(Reservation, id=reservation_id)
        service_item = get_object_or_404(ServiceItem, id=item_id)

        charge = ServiceCharge.objects.create(
            reservation=reservation,
            item_name=service_item.item_name,
            price=service_item.price,
            quantity=quantity
        )

        return Response({
            "message": f"Đã thêm {quantity} {service_item.item_name}",
            "charge": {
                "item_name": charge.item_name,
                "total_price": charge.total_price
            }
        }, status=status.HTTP_201_CREATED)
    
# --- 5. API Check-out ---
class CheckoutAPIView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, reservation_id):
        """API xem trước hóa đơn (Tạm tính)"""
        reservation = get_object_or_404(Reservation, id=reservation_id)
        room = reservation.room

        check_out_time = timezone.now()
        duration = check_out_time - reservation.check_in_date
        num_nights = duration.days
        
        if duration.seconds >= 6 * 3600 or (num_nights == 0 and duration.seconds > 0):
            num_nights += 1
        if num_nights == 0: num_nights = 1

        total_room_cost = num_nights * room.price_per_night
        service_charges = ServiceCharge.objects.filter(reservation=reservation)
        total_service_cost = sum(charge.total_price for charge in service_charges)
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

        reservation.status = 'Completed'
        reservation.check_out_date = timezone.now()
        reservation.save()

        room.status = 'Vacant' # Hoặc 'Dirty' nếu muốn quy trình dọn dẹp
        room.save()

        return Response({"message": f"Đã trả phòng {room.room_number} thành công. Tổng thu: {request.data.get('final_bill', 0)}"})

# --- 6. API Check-in (Cho khách đã đặt trước) ---
class CheckinAPIView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, reservation_id):
        reservation = get_object_or_404(Reservation, id=reservation_id)
        room = reservation.room

        if reservation.status != 'Confirmed':
            return Response({"error": "Booking này không ở trạng thái chờ Check-in."}, status=400)
        
        reservation.status = 'Occupied'
        reservation.check_in_date = timezone.now()
        reservation.save()

        room.status = 'Occupied'
        room.save()

        return Response({"message": f"Check-in thành công cho phòng {room.room_number}"})
    
# --- 7. API Walk-in Check-in (Khách vãng lai) ---
class WalkInCheckinAPIView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, room_id):
        room = get_object_or_404(Room, id=room_id)
        
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
                        'address': address if address else 'Khách vãng lai',
                        'license_plate': license_plate,
                        'id_type': 'CCCD'
                    }
                )
                
                if not created:
                    guest.full_name = full_name
                    guest.phone = phone
                    if dob: guest.dob = dob
                    if address: guest.address = address
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

# ==========================================================
# CÁC API MỚI BỔ SUNG ĐỂ FULL TÍNH NĂNG
# ==========================================================

# --- 8. API Quản lý Khách hàng (CRUD) ---
class GuestViewSet(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]
    queryset = Guest.objects.all().order_by('-created_at')
    serializer_class = GuestSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['full_name', 'phone', 'id_number']

# --- 9. API Quản lý Đặt phòng (Tạo, Xem, Hủy) ---
class BookingViewSet(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]
    queryset = Reservation.objects.all().order_by('-created_at')
    serializer_class = ReservationSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['guest__full_name', 'room__room_number']

    def create(self, request, *args, **kwargs):
        """API Tạo đặt phòng trước"""
        serializer = CreateReservationSerializer(data=request.data)
        if serializer.is_valid():
            data = serializer.validated_data
            room = get_object_or_404(Room, id=data['room_id'])
            
            # Xử lý thông tin khách hàng
            guest = None
            if data.get('guest_id'):
                guest = get_object_or_404(Guest, id=data['guest_id'])
            elif data.get('guest_id_number'):
                guest, created = Guest.objects.get_or_create(
                    id_number=data['guest_id_number'],
                    defaults={
                        'full_name': data.get('guest_name', 'Unknown'),
                        'phone': data.get('guest_phone', ''),
                        'address': 'Khách đặt qua App'
                    }
                )
            else:
                return Response({"error": "Cần cung cấp ID khách hoặc thông tin khách mới"}, status=400)

            # Tạo Booking
            reservation = Reservation.objects.create(
                room=room,
                guest=guest,
                check_in_date=data['check_in_date'],
                check_out_date=data['check_out_date'],
                deposit=data['deposit'],
                note=data.get('note', ''),
                status='Confirmed'
            )
            
            if room.status == 'Vacant':
                room.status = 'Booked'
                room.save()

            return Response(ReservationSerializer(reservation).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, *args, **kwargs):
        """API Hủy đặt phòng"""
        reservation = self.get_object()
        if reservation.status == 'Occupied':
            return Response({"error": "Không thể hủy phòng đang có khách ở."}, status=400)
        
        reservation.status = 'Cancelled'
        reservation.save()
        
        room = reservation.room
        if room.status == 'Booked':
            room.status = 'Vacant'
            room.save()
            
        return Response({"message": "Đã hủy đặt phòng thành công"})

# --- 10. API Xem lịch làm việc ---
class StaffScheduleAPIView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        today = timezone.now().date()
        schedules = StaffSchedule.objects.filter(date__gte=today).order_by('date')
        serializer = StaffScheduleSerializer(schedules, many=True)
        return Response(serializer.data)

# --- 11. API Thống kê nhanh ---
class ManagementStatsAPIView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        today = timezone.now().date()
        
        completed_bookings = Reservation.objects.filter(
            status='Completed', 
            check_out_date__date=today
        )
        
        return Response({
            "total_rooms": Room.objects.count(),
            "occupied_rooms": Room.objects.filter(status='Occupied').count(),
            "vacant_rooms": Room.objects.filter(status='Vacant').count(),
            "guests_in_house": Reservation.objects.filter(status='Occupied').count(),
            "pending_requests": GuestRequest.objects.filter(status='New').count(),
            "today_checkouts": completed_bookings.count()
        })
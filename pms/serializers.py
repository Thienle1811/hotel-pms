from rest_framework import serializers
from .models import Hotel, Room, Guest, Reservation, ServiceItem, ServiceCharge, GuestRequest, StaffSchedule

class HotelSerializer(serializers.ModelSerializer):
    class Meta:
        model = Hotel
        fields = '__all__'

class RoomSerializer(serializers.ModelSerializer):
    # Hiển thị tên trạng thái thay vì mã (ví dụ: "Trống (Xanh)" thay vì "Vacant")
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = Room
        fields = ['id', 'room_number', 'room_type', 'price_per_night', 'status', 'status_display', 'hotel']

class GuestSerializer(serializers.ModelSerializer):
    class Meta:
        model = Guest
        fields = '__all__'

class ReservationSerializer(serializers.ModelSerializer):
    guest_name = serializers.CharField(source='guest.full_name', read_only=True)
    room_number = serializers.CharField(source='room.room_number', read_only=True)
    
    class Meta:
        model = Reservation
        fields = ['id', 'room', 'room_number', 'guest', 'guest_name', 'check_in_date', 'check_out_date', 'deposit', 'status', 'note', 'created_at']

class ServiceItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceItem
        fields = '__all__'

class GuestRequestSerializer(serializers.ModelSerializer):
    room_number = serializers.CharField(source='room.room_number', read_only=True)
    
    class Meta:
        model = GuestRequest
        fields = ['id', 'room', 'room_number', 'content', 'status', 'created_at']

class ServiceChargeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceCharge
        fields = ['id', 'item_name', 'quantity', 'price', 'total_price', 'created_at']

# --- MỚI THÊM ---
class StaffScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = StaffSchedule
        fields = '__all__'

class CreateReservationSerializer(serializers.Serializer):
    """Serializer dùng để validate dữ liệu khi tạo đặt phòng trước"""
    room_id = serializers.IntegerField()
    # Thông tin khách hàng (có thể chọn khách cũ hoặc tạo mới)
    guest_id = serializers.IntegerField(required=False, allow_null=True)
    guest_name = serializers.CharField(required=False, allow_blank=True)
    guest_phone = serializers.CharField(required=False, allow_blank=True)
    guest_id_number = serializers.CharField(required=False, allow_blank=True)
    
    check_in_date = serializers.DateTimeField()
    check_out_date = serializers.DateTimeField()
    deposit = serializers.DecimalField(max_digits=10, decimal_places=0, required=False, default=0)
    note = serializers.CharField(required=False, allow_blank=True)  
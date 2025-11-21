from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db.models import Q 

# Model cho chuỗi khách sạn (Hotel) - Chuẩn bị cho việc mở rộng 7 cơ sở
class Hotel(models.Model):
    name = models.CharField(max_length=255, verbose_name="Tên Khách sạn")
    code = models.CharField(max_length=50, unique=True, verbose_name="Mã Khách sạn") 
    
    def __str__(self):
        return self.name
        
    class Meta:
        verbose_name = "1. Khách sạn"
        verbose_name_plural = "1. Quản lý Khách sạn"

# Model cho Phòng (Room)
class Room(models.Model):
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, verbose_name="Khách sạn")
    room_number = models.CharField(max_length=10, unique=True, verbose_name="Số Phòng")
    room_type = models.CharField(max_length=50, verbose_name="Loại Phòng")
    price_per_night = models.DecimalField(max_digits=10, decimal_places=0, default=500000, verbose_name="Giá/Đêm")
    
    # Trạng thái phòng: Vacant (Trống), Dirty (Cần dọn), Occupied (Có khách), Booked (Đã đặt)
    STATUS_CHOICES = [
        ('Vacant', 'Trống (Xanh)'),
        ('Dirty', 'Cần dọn (Xám)'),
        ('Occupied', 'Đang có khách (Đỏ)'),
        ('Booked', 'Đã đặt (Vàng)'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Vacant', verbose_name="Trạng thái")

    def __str__(self):
        return f"Phòng {self.room_number} ({self.room_type}) - {self.hotel.code}"
        
    class Meta:
        verbose_name = "2. Phòng"
        verbose_name_plural = "2. Quản lý Phòng"
        ordering = ['room_number']
        
# Model cho Khách hàng (Guest) - Chứa thông tin đăng ký tạm trú
class Guest(models.Model):
    full_name = models.CharField(max_length=255, verbose_name="Họ và Tên")
    dob = models.DateField(null=True, blank=True, verbose_name="Ngày sinh") # Bắt buộc cho Đăng ký tạm trú
    
    ID_TYPE_CHOICES = [
        ('CCCD', 'Căn cước Công dân'),
        ('CMND', 'Chứng minh Nhân dân'),
        ('PP', 'Hộ chiếu (Passport)'),
        ('OTHER', 'Khác')
    ]
    id_type = models.CharField(max_length=10, choices=ID_TYPE_CHOICES, default='CCCD', verbose_name="Loại giấy tờ")
    id_number = models.CharField(max_length=50, unique=True, verbose_name="Mã số giấy tờ") # Mã số giấy tờ (Key cho OCR)
    license_plate = models.CharField(max_length=20, null=True, blank=True, verbose_name="Biển số xe")
    address = models.CharField(max_length=500, verbose_name="Địa chỉ thường trú")
    phone = models.CharField(max_length=20, null=True, blank=True, verbose_name="Số điện thoại")
    
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.full_name
        
    class Meta:
        verbose_name = "3. Khách hàng"
        verbose_name_plural = "3. Quản lý Khách hàng"

# Model cho Đặt phòng (Reservation)
class Reservation(models.Model):
    room = models.ForeignKey(Room, on_delete=models.CASCADE, verbose_name="Phòng")
    guest = models.ForeignKey(Guest, on_delete=models.CASCADE, verbose_name="Khách hàng")
    
    # Check-in bắt buộc, Check-out linh hoạt (có thể NULL)
    check_in_date = models.DateTimeField(verbose_name="Thời gian Check-in")
    check_out_date = models.DateTimeField(null=True, blank=True, verbose_name="Thời gian Check-out dự kiến")
    
    # Trạng thái đặt phòng: Confirmed (đã xác nhận), Occupied (đang cư trú), Completed (đã hoàn tất)
    STATUS_CHOICES = [
        ('Confirmed', 'Đã xác nhận (Booking)'),
        ('Occupied', 'Đang cư trú'),
        ('Completed', 'Đã hoàn tất'),
        ('Cancelled', 'Đã hủy'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Confirmed', verbose_name="Trạng thái đặt phòng")
    
    note = models.TextField(blank=True, verbose_name="Ghi chú")
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Phòng {self.room.room_number} - {self.guest.full_name} ({self.status})"

    class Meta:
        verbose_name = "4. Đặt phòng"
        verbose_name_plural = "4. Quản lý Đặt phòng"
        ordering = ['check_in_date']

    # *** PHƯƠNG THỨC CLEAN() ĐÃ ĐƯỢC CHUYỂN VÀO FORM VÀ VIEW ĐỂ TRÁNH LỖI related_descriptors.py ***

# Model cho Dịch vụ/Phụ phí (ServiceCharge)
class ServiceCharge(models.Model):
    reservation = models.ForeignKey(Reservation, on_delete=models.CASCADE, verbose_name="Đặt phòng")
    item_name = models.CharField(max_length=100, verbose_name="Tên Dịch vụ/Sản phẩm")
    quantity = models.IntegerField(default=1, verbose_name="Số lượng")
    price = models.DecimalField(max_digits=10, decimal_places=0, verbose_name="Đơn giá") # Giá tại thời điểm tính phí
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Dịch vụ {self.item_name} x {self.quantity} cho phòng {self.reservation.room.room_number}"

    @property
    def total_price(self):
        return self.quantity * self.price
        
    class Meta:
        verbose_name = "5. Dịch vụ"
        verbose_name_plural = "5. Quản lý Dịch vụ & Phụ phí"

# Model cho Yêu cầu Khách hàng (GuestRequest) - Từ QR Code
class GuestRequest(models.Model):
    room = models.ForeignKey(Room, on_delete=models.CASCADE, verbose_name="Phòng yêu cầu") 
    reservation = models.ForeignKey(Reservation, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Booking liên quan")
    content = models.TextField(verbose_name="Nội dung yêu cầu")
    
    STATUS_CHOICES = [
        ('New', 'Mới'),
        ('Processing', 'Đang xử lý'),
        ('Completed', 'Hoàn thành'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='New', verbose_name="Trạng thái")
    
    assigned_staff = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Giao cho nhân viên")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Yêu cầu từ P.{self.room.room_number}: {self.content[:30]}..."
        
    class Meta:
        verbose_name = "6. Yêu cầu Khách"
        verbose_name_plural = "6. Quản lý Yêu cầu Khách"

# Model cho Danh mục Dịch vụ/Sản phẩm (Service Item Inventory)
class ServiceItem(models.Model):
    item_name = models.CharField(max_length=100, unique=True, verbose_name="Tên Dịch vụ/Sản phẩm")
    price = models.DecimalField(max_digits=10, decimal_places=0, verbose_name="Đơn giá hiện tại")
    
    def __str__(self):
        return f"{self.item_name} ({self.price:,} VND)"
        
    class Meta:
        verbose_name = "7. Danh mục Dịch vụ"
        verbose_name_plural = "7. Quản lý Danh mục Dịch vụ"

class StaffSchedule(models.Model):
    ROLE_CHOICES = [
        ('Reception', 'Lễ tân'),
        ('Housekeeping', 'Buồng phòng'),
        ('Guard', 'Bảo vệ'),
    ]
    
    SHIFT_CHOICES = [
        ('Morning', 'Ca Sáng (6h-14h)'),
        ('Afternoon', 'Ca Chiều (14h-22h)'),
        ('Night', 'Ca Đêm (22h-6h)'),
    ]

    staff_name = models.CharField(max_length=100, verbose_name="Tên Nhân viên")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, verbose_name="Vị trí")
    date = models.DateField(verbose_name="Ngày làm việc")
    shift = models.CharField(max_length=20, choices=SHIFT_CHOICES, verbose_name="Ca làm việc")
    note = models.TextField(blank=True, null=True, verbose_name="Ghi chú")

    def __str__(self):
        return f"{self.staff_name} - {self.get_shift_display()} ({self.date})"

    class Meta:
        verbose_name = "8. Lịch làm việc"
        verbose_name_plural = "8. Quản lý Lịch làm việc"
        ordering = ['-date', 'shift']
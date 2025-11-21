from django import forms
from .models import Guest, Reservation, ServiceCharge, ServiceItem
from django.utils import timezone
from .models import StaffSchedule
from django.contrib.auth.models import User

class GuestForm(forms.ModelForm):
    class Meta:
        model = Guest
        # 👇 Thêm 'photo' vào danh sách này
        fields = [
            'full_name', 'dob', 'id_type', 
            'id_number', 'photo', 'license_plate', 'address', 'phone' 
        ] 
        # (Tôi đã đặt 'photo' ngay sau 'id_number' để nó hiện gần nhau)
        
        widgets = {
            'dob': forms.DateInput(attrs={'type': 'date'}),
            # Có thể thêm widget cho photo nếu muốn custom, nhưng mặc định là đủ dùng
        }
        labels = {
            'full_name': 'Họ và Tên',
            'dob': 'Ngày sinh',
            'id_type': 'Loại giấy tờ',
            'id_number': 'Mã số giấy tờ',
            'photo': 'Ảnh giấy tờ (CCCD/Passport)', # <--- Thêm nhãn hiển thị
            'address': 'Địa chỉ thường trú',
            'phone': 'Số điện thoại',
            'license_plate': 'Biển số xe',
        }

class ReservationForm(forms.ModelForm):
    """
    Form để tạo Booking và Check-in.
    """
    class Meta:
        model = Reservation
        fields = [
            'check_in_date', 
            'check_out_date',
            'status',
            'note',
        ]
        
        widgets = {
            'check_in_date': forms.DateTimeInput(
                attrs={'type': 'datetime-local'},
                format='%Y-%m-%dT%H:%M'
            ),
            'check_out_date': forms.DateTimeInput(
                attrs={'type': 'datetime-local'},
                format='%Y-%m-%dT%H:%M'
            ),
        }
        
        labels = {
            'check_in_date': 'Thời gian Check-in',
            'check_out_date': 'Thời gian Check-out dự kiến',
            'status': 'Trạng thái đặt phòng',
            'note': 'Ghi chú',
        }

    def clean(self):
        cleaned_data = super().clean()
        check_in_date = cleaned_data.get("check_in_date")
        check_out_date = cleaned_data.get("check_out_date")

        if check_in_date and check_out_date and check_out_date <= check_in_date:
            self.add_error('check_out_date', "Ngày Check-out phải sau ngày Check-in.")
            
        return cleaned_data
        
class ServiceChargeForm(forms.ModelForm):
    """
    Form để thêm phụ phí/dịch vụ vào Reservation.
    """
    class Meta:
        model = ServiceCharge
        # Loại bỏ trường reservation vì nó sẽ được gán trong view
        fields = ['item_name', 'quantity', 'price']
        
        widgets = {
            'quantity': forms.NumberInput(attrs={'min': 1}),
        }
        labels = {
            'item_name': 'Tên Dịch vụ/Sản phẩm',
            'quantity': 'Số lượng',
            'price': 'Đơn giá (VND)',
        }

class ServiceItemForm(forms.ModelForm):
    """
    Form cho Admin/Quản lý để thêm/sửa Danh mục Dịch vụ (Minibar, Laundry...).
    """
    class Meta:
        model = ServiceItem
        fields = ['item_name', 'price']
        labels = {
            'item_name': 'Tên Dịch vụ/Sản phẩm',
            'price': 'Đơn giá (VND)',
        }
        widgets = {
             'price': forms.NumberInput(attrs={'min': 0}),
        }

class StaffScheduleForm(forms.ModelForm):
    """
    Form để thêm lịch làm việc (Đã nâng cấp Dropdown)
    """
    # 1. Tạo Dropdown chọn nhân viên từ danh sách tài khoản
    selected_user = forms.ModelChoiceField(
        queryset=User.objects.all().order_by('username'),
        label="Chọn Nhân viên",
        empty_label="-- Vui lòng chọn --"
    )

    class Meta:
        model = StaffSchedule
        # 2. Chỉ hiển thị các trường cần thiết (Bỏ staff_name và role)
        fields = ['date', 'shift', 'note'] 
        
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'note': forms.Textarea(attrs={'rows': 3}),
        }
        
        labels = {
            'date': 'Ngày làm việc',
            'shift': 'Ca làm việc',
            'note': 'Ghi chú',
        }

    # Tùy chỉnh hiển thị tên trong Dropdown (Hiện Họ tên thật thay vì user ID)
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['selected_user'].label_from_instance = lambda obj: f"{obj.last_name} {obj.first_name} ({obj.username})"
class StaffUserForm(forms.ModelForm):
    """Form tạo nhân viên mới"""
    password = forms.CharField(widget=forms.PasswordInput(), label="Mật khẩu")
    role = forms.ChoiceField(
        choices=[('Receptionist', 'Lễ tân (Chỉ xem 4 mục)'), ('Manager', 'Quản lý (Full quyền)')],
        label="Phân quyền",
        initial='Receptionist'
    )

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'password']
        labels = {
            'username': 'Tên đăng nhập',
            'first_name': 'Họ',
            'last_name': 'Tên',
            'email': 'Email'
        }
    
    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password"]) # Mã hóa mật khẩu
        if commit:
            user.save()
        return user
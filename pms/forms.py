from django import forms
from .models import Guest, Reservation, ServiceCharge, ServiceItem, StaffSchedule
from django.contrib.auth.models import User

class GuestForm(forms.ModelForm):
    class Meta:
        model = Guest
        fields = [
            'full_name', 'dob', 'id_type', 
            'id_number', 'photo_front', 'photo_back', 
            'license_plate', 'address', 'phone'
        ]
        widgets = {
            # Sử dụng class 'datepicker' cho ngày sinh
            'dob': forms.DateInput(attrs={'class': 'datepicker', 'placeholder': 'dd/mm/yyyy'}, format='%d/%m/%Y'),
            'full_name': forms.TextInput(attrs={'placeholder': 'Nguyễn Văn A'}),
            'id_number': forms.TextInput(attrs={'placeholder': 'Số CCCD/Hộ chiếu'}),
        }
        labels = {
            'full_name': 'Họ và Tên',
            'dob': 'Ngày sinh',
            'id_type': 'Loại giấy tờ',
            'id_number': 'Mã số giấy tờ',
            'photo_front': 'Ảnh mặt trước (CCCD)',
            'photo_back': 'Ảnh mặt sau (CCCD)',
            'address': 'Địa chỉ thường trú',
            'phone': 'Số điện thoại',
            'license_plate': 'Biển số xe',
        }

class ReservationForm(forms.ModelForm):
    class Meta:
        model = Reservation
        fields = ['check_in_date', 'check_out_date', 'deposit', 'status', 'note']
        
        widgets = {
            # --- [THAY ĐỔI] Dùng class 'datetimepicker' thay vì type='datetime-local' ---
            'check_in_date': forms.DateTimeInput(
                attrs={'class': 'datetimepicker', 'placeholder': 'Chọn giờ vào...'}, 
                format='%d/%m/%Y %H:%M'
            ),
            'check_out_date': forms.DateTimeInput(
                attrs={'class': 'datetimepicker', 'placeholder': 'Chọn giờ ra...'}, 
                format='%d/%m/%Y %H:%M'
            ),
            # ---------------------------------------------------------------------------
            'deposit': forms.NumberInput(attrs={'min': 0, 'step': 10000, 'placeholder': 'Nhập số tiền cọc (nếu có)'}),
        }
        labels = {
            'check_in_date': 'Thời gian Check-in',
            'check_out_date': 'Thời gian Check-out dự kiến',
            'deposit': 'Tiền đặt cọc (VND)', 
            'status': 'Trạng thái',
            'note': 'Ghi chú',
        }
    
    def clean(self):
        cleaned_data = super().clean()
        check_in = cleaned_data.get("check_in_date")
        check_out = cleaned_data.get("check_out_date")
        if check_in and check_out and check_out <= check_in:
            self.add_error('check_out_date', "Ngày Check-out phải sau ngày Check-in.")
        return cleaned_data

class ServiceChargeForm(forms.ModelForm):
    class Meta:
        model = ServiceCharge
        fields = ['item_name', 'quantity', 'price']
        widgets = {'quantity': forms.NumberInput(attrs={'min': 1})}
        labels = {'item_name': 'Tên Dịch vụ', 'quantity': 'Số lượng', 'price': 'Đơn giá'}

class ServiceItemForm(forms.ModelForm):
    class Meta:
        model = ServiceItem
        fields = ['item_name', 'price']
        widgets = {'price': forms.NumberInput(attrs={'min': 0})}
        labels = {'item_name': 'Tên Dịch vụ', 'price': 'Đơn giá'}

class StaffScheduleForm(forms.ModelForm):
    selected_user = forms.ModelChoiceField(queryset=User.objects.all().order_by('username'), label="Chọn Nhân viên", empty_label="-- Chọn --")
    class Meta:
        model = StaffSchedule
        fields = ['date', 'shift', 'note'] 
        widgets = {'date': forms.DateInput(attrs={'type': 'date'}), 'note': forms.Textarea(attrs={'rows': 3})}
        labels = {'date': 'Ngày làm', 'shift': 'Ca làm', 'note': 'Ghi chú'}
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['selected_user'].label_from_instance = lambda obj: f"{obj.last_name} {obj.first_name} ({obj.username})"

class StaffUserForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput(), label="Mật khẩu")
    role = forms.ChoiceField(choices=[('Manager', 'Quản lý'), ('Receptionist', 'Lễ tân'), ('Housekeeping', 'Buồng phòng')], label="Phân quyền", initial='Receptionist')
    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'password']
        labels = {'username': 'Tên đăng nhập', 'first_name': 'Họ', 'last_name': 'Tên', 'email': 'Email'}
    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password"])
        if commit: user.save()
        return user
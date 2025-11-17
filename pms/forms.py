from django import forms
from .models import Guest, Reservation, ServiceCharge, ServiceItem
from django.utils import timezone

class GuestForm(forms.ModelForm):
    """
    Form để nhập liệu thông tin Khách hàng (bao gồm cả thông tin đăng ký tạm trú).
    """
    class Meta:
        model = Guest
        fields = [
            'full_name', 'dob', 'id_type', 
            'id_number', 'address', 'phone'
        ]
        widgets = {
            'dob': forms.DateInput(attrs={'type': 'date'}),
        }
        labels = {
            'full_name': 'Họ và Tên',
            'dob': 'Ngày sinh',
            'id_type': 'Loại giấy tờ',
            'id_number': 'Mã số giấy tờ',
            'address': 'Địa chỉ thường trú',
            'phone': 'Số điện thoại',
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
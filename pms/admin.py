from django.contrib import admin
from .models import Hotel, Room, Guest, Reservation, ServiceCharge, GuestRequest, StaffSchedule

# Đăng ký các models
admin.site.register(Hotel)
admin.site.register(Room)
admin.site.register(Guest)
admin.site.register(Reservation)
admin.site.register(ServiceCharge)
admin.site.register(GuestRequest)
admin.site.register(StaffSchedule)
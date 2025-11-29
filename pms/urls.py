from django.urls import path, include
from . import views
from . import api_views  # Import file api_views
from django.contrib.auth.views import LoginView, LogoutView
from rest_framework.routers import DefaultRouter  # Import Router của DRF
from rest_framework.authtoken.views import obtain_auth_token

# --- CẤU HÌNH ROUTER CHO API ---
router = DefaultRouter()
router.register(r'services', api_views.ServiceItemViewSet)
router.register(r'guest-requests', api_views.GuestRequestViewSet)
# 👇 MỚI THÊM CHO APP FULL TÍNH NĂNG
router.register(r'guests', api_views.GuestViewSet)
router.register(r'bookings', api_views.BookingViewSet)

urlpatterns = [
    # =========================================
    # PHẦN WEB APP (Giữ nguyên)
    # =========================================
    
    # LOGIN / LOGOUT
    path('login/', LoginView.as_view(template_name='pms/login.html'), name='login'),
    path('logout/', views.custom_logout, name='logout'),
    
    # DASHBOARD
    path('', views.dashboard, name='dashboard'), 

    path('guests/', views.manage_guests, name='manage-guests'),
    path('guests/edit/<int:guest_id>/', views.edit_guest, name='edit-guest'),
    path('guests/delete/<int:guest_id>/', views.delete_guest, name='delete-guest'),
    
    # QUẢN LÝ PHÒNG
    path('rooms/manage/', views.manage_rooms, name='manage-rooms'),
    path('rooms/add/', views.room_create, name='room-create'),
    path('rooms/edit/<int:room_id>/', views.room_edit, name='room-edit'),
    path('rooms/delete/<int:room_id>/', views.delete_room, name='delete-room'),
    path('rooms/qr/<int:room_id>/', views.room_qr_code, name='room-qr-code'), 
    
    # NGHIỆP VỤ
    path('room/<int:room_id>/booking/', views.create_booking, name='create-booking'),
    path('reservation/<int:reservation_id>/checkin/', views.perform_check_in, name='perform-check-in'),
    path('reservation/<int:reservation_id>/bill/', views.billing_details, name='billing-details'), 
    path('reservation/<int:reservation_id>/checkout/', views.perform_check_out, name='perform-check-out'),
    path('booking/cancel/<int:reservation_id>/', views.cancel_booking, name='cancel-booking'),
    path('booking-management/', views.booking_management, name='booking-management'),
    
    # XUẤT FILE & REQUEST
    path('export/registry/', views.export_temporary_registry, name='export-registry'),
    path('guest/request/<int:room_id>/', views.guest_request_portal, name='guest-request-portal'),
    path('requests/', views.manage_requests, name='manage-requests'), 
    path('requests/complete/<int:request_id>/', views.complete_request, name='complete-request'),
    path('ajax/new-requests-count/', views.check_new_requests_count, name='ajax-new-requests-count'),
    
    # LỊCH & DỊCH VỤ
    path('reservations/calendar/', views.reservation_calendar, name='reservation-calendar'),
    path('services/inventory/', views.manage_service_inventory, name='manage-service-inventory'),
    path('services/inventory/create/', views.service_item_create, name='service-item-create'),
    path('services/inventory/edit/<int:item_id>/', views.service_item_edit, name='service-item-edit'),
    path('services/inventory/delete/<int:item_id>/', views.service_item_delete, name='service-item-delete'),
    path('reservation/<int:reservation_id>/services/', views.manage_room_services, name='manage-room-services'),
    path('reservation/<int:reservation_id>/services/add/', views.add_service_charge, name='add-service-charge'),

    # QUẢN LÝ
    path('management/', views.management_dashboard, name='management-dashboard'),
    path('management/schedule/add/', views.add_staff_schedule, name='add-staff-schedule'),
    path('management/staff/', views.manage_staff, name='manage-staff'),
    path('management/staff/delete/<int:user_id>/', views.delete_staff, name='delete-staff'),

    # =========================================
    # PHẦN API CHO ANDROID APP
    # =========================================
    
    # Router URLs (Bao gồm guests, bookings, services, guest-requests)
    path('api/', include(router.urls)),
    
    # API Authentication
    path('api/login/', obtain_auth_token, name='api_token_auth'),
    
    # API Dashboard & Room Detail
    path('api/dashboard/', api_views.DashboardAPIView.as_view(), name='api-dashboard'),
    path('api/room/<int:room_id>/', api_views.RoomDetailAPIView.as_view(), name='api-room-detail'),

    # API Nghiệp vụ Lễ tân
    path('api/add-service/', api_views.AddServiceChargeAPIView.as_view(), name='api-add-service'),
    path('api/reservation/<int:reservation_id>/checkout/', api_views.CheckoutAPIView.as_view(), name='api-checkout'),
    path('api/reservation/<int:reservation_id>/checkin/', api_views.CheckinAPIView.as_view(), name='api-checkin'),
    path('api/room/<int:room_id>/walk-in/', api_views.WalkInCheckinAPIView.as_view(), name='api-walk-in'),

    # 👇 MỚI THÊM
    path('api/staff-schedule/', api_views.StaffScheduleAPIView.as_view(), name='api-staff-schedule'),
    path('api/management-stats/', api_views.ManagementStatsAPIView.as_view(), name='api-management-stats'),
]
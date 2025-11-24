from django.urls import path, include
from . import views
from . import api_views  # Import file api_views mới tạo
from django.contrib.auth.views import LoginView, LogoutView
from rest_framework.routers import DefaultRouter  # Import Router của DRF
from rest_framework.authtoken.views import obtain_auth_token

# --- CẤU HÌNH ROUTER CHO API ---
# Router sẽ tự động tạo các URL (GET, POST, PUT, DELETE) cho ViewSets
router = DefaultRouter()
router.register(r'services', api_views.ServiceItemViewSet)
router.register(r'guest-requests', api_views.GuestRequestViewSet)

urlpatterns = [
    # =========================================
    # PHẦN WEB APP (Cũ - Giữ nguyên)
    # =========================================
    
    # LOGIN / LOGOUT
    path('login/', LoginView.as_view(template_name='pms/login.html'), name='login'),
    path('logout/', views.custom_logout, name='logout'),
    
    # DASHBOARD - Trang chủ
    path('', views.dashboard, name='dashboard'), 

    path('guests/', views.manage_guests, name='manage-guests'),
    
    # QUẢN LÝ PHÒNG VÀ QR CODE
    path('rooms/manage/', views.manage_rooms, name='manage-rooms'),
    path('rooms/add/', views.room_create, name='room-create'),
    path('rooms/edit/<int:room_id>/', views.room_edit, name='room-edit'),
    path('rooms/qr/<int:room_id>/', views.room_qr_code, name='room-qr-code'), 
    
    # CHỨC NĂNG NGHIỆP VỤ CHÍNH
    path('room/<int:room_id>/booking/', views.create_booking, name='create-booking'),
    path('reservation/<int:reservation_id>/checkin/', views.perform_check_in, name='perform-check-in'),
    
    # HÓA ĐƠN VÀ CHECK-OUT
    path('reservation/<int:reservation_id>/bill/', views.billing_details, name='billing-details'), 
    path('reservation/<int:reservation_id>/checkout/', views.perform_check_out, name='perform-check-out'),
    
    # XUẤT FILE EXCEL
    path('export/registry/', views.export_temporary_registry, name='export-registry'),
    
    # QUẢN LÝ YÊU CẦU KHÁCH HÀNG (QR CODE PORTAL)
    path('guest/request/<int:room_id>/', views.guest_request_portal, name='guest-request-portal'),
    path('requests/', views.manage_requests, name='manage-requests'), 
    path('requests/complete/<int:request_id>/', views.complete_request, name='complete-request'),
    
    # LỊCH ĐẶT PHÒNG
    path('reservations/calendar/', views.reservation_calendar, name='reservation-calendar'),
    
    # QUẢN LÝ DANH MỤC DỊCH VỤ (SERVICE ITEM INVENTORY)
    path('services/inventory/', views.manage_service_inventory, name='manage-service-inventory'),
    path('services/inventory/create/', views.service_item_create, name='service-item-create'),
    path('services/inventory/edit/<int:item_id>/', views.service_item_edit, name='service-item-edit'),
    path('services/inventory/delete/<int:item_id>/', views.service_item_delete, name='service-item-delete'),

    # QUẢN LÝ GIAO DỊCH DỊCH VỤ (GẮN VỚI PHÒNG)
    path('reservation/<int:reservation_id>/services/', views.manage_room_services, name='manage-room-services'),
    path('reservation/<int:reservation_id>/services/add/', views.add_service_charge, name='add-service-charge'),

    # =========================================
    # PHẦN API CHO ANDROID APP (Mới thêm)
    # =========================================
    
    # Bao gồm các URL tự động sinh ra từ Router (services/, guest-requests/)
    path('api/', include(router.urls)),
    
    # API Dashboard (Trả về JSON danh sách phòng)
    path('api/dashboard/', api_views.DashboardAPIView.as_view(), name='api-dashboard'),
    
    # API Chi tiết phòng
    path('api/room/<int:room_id>/', api_views.RoomDetailAPIView.as_view(), name='api-room-detail'),

    path('api/login/', obtain_auth_token, name='api_token_auth'),

    path('api/add-service/', api_views.AddServiceChargeAPIView.as_view(), name='api-add-service'),
    path('api/reservation/<int:reservation_id>/checkout/', api_views.CheckoutAPIView.as_view(), name='api-checkout'),
    path('api/reservation/<int:reservation_id>/checkin/', api_views.CheckinAPIView.as_view(), name='api-checkin'),
    path('api/room/<int:room_id>/walk-in/', api_views.WalkInCheckinAPIView.as_view(), name='api-walk-in'),
    path('guests/edit/<int:guest_id>/', views.edit_guest, name='edit-guest'),
    path('guests/delete/<int:guest_id>/', views.delete_guest, name='delete-guest'),
    path('rooms/delete/<int:room_id>/', views.delete_room, name='delete-room'),
    path('management/', views.management_dashboard, name='management-dashboard'),
    path('ajax/new-requests-count/', views.check_new_requests_count, name='ajax-new-requests-count'),
    path('management/schedule/add/', views.add_staff_schedule, name='add-staff-schedule'),
    path('management/staff/', views.manage_staff, name='manage-staff'),
    path('management/staff/delete/<int:user_id>/', views.delete_staff, name='delete-staff'),
    path('booking/cancel/<int:reservation_id>/', views.cancel_booking, name='cancel-booking'),
    path('booking-management/', views.booking_management, name='booking-management'),
]
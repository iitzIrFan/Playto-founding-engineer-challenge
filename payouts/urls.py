from django.urls import path

from payouts.views import DashboardView, MerchantListView, PayoutCreateView

urlpatterns = [
    path("payouts", PayoutCreateView.as_view(), name="payout-create"),
    path("merchants", MerchantListView.as_view(), name="merchant-list"),
    path("dashboard", DashboardView.as_view(), name="dashboard"),
]

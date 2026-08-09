from django.contrib import admin

from .models import LSA, Booking, Parent, Payment

admin.site.register(Parent)
admin.site.register(LSA)
admin.site.register(Booking)


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    # reference_id is editable=False on the model (it's system-generated),
    # so it's hidden from the form by default. Listing it as read-only
    # makes it visible without allowing accidental edits.
    readonly_fields = ["reference_id"]
    list_display = ["id", "booking", "reference_id", "amount", "status"]

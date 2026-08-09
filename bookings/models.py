import uuid

from django.core.exceptions import ValidationError
from django.db import models


class Parent(models.Model):
    """A parent/guardian who books sessions on behalf of a child."""

    name = models.CharField(max_length=150)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["email"]),
        ]

    def __str__(self):
        return self.name


class LSA(models.Model):
    """
    Learning Session Assistant (tutor/counsellor) who conducts sessions.
    """

    name = models.CharField(max_length=150)
    email = models.EmailField(unique=True)
    subject = models.CharField(max_length=100, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["is_active", "subject"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.subject})"


class Booking(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending Payment"
        CONFIRMED = "confirmed", "Confirmed"
        CANCELLED = "cancelled", "Cancelled"
        COMPLETED = "completed", "Completed"

    parent = models.ForeignKey(
        Parent, on_delete=models.CASCADE, related_name="bookings"
    )
    lsa = models.ForeignKey(LSA, on_delete=models.CASCADE, related_name="bookings")
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Bookings in these states are treated as "occupying" the LSA's calendar.
    ACTIVE_STATUSES = (Status.PENDING, Status.CONFIRMED)

    class Meta:
        indexes = [
            # Speeds up the overlap-lookup query: same LSA, time-window filter.
            models.Index(fields=["lsa", "start_time", "end_time"]),
            models.Index(fields=["status"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_time__gt=models.F("start_time")),
                name="booking_end_after_start",
            )
        ]

    def clean(self):
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValidationError("end_time must be after start_time.")

    def __str__(self):
        return f"Booking#{self.pk} {self.lsa} for {self.parent} @ {self.start_time}"


class Payment(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"

    booking = models.OneToOneField(
        Booking, on_delete=models.CASCADE, related_name="payment"
    )
    reference_id = models.CharField(
        max_length=64, unique=True, default=uuid.uuid4, editable=False
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["reference_id"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"Payment#{self.pk} for {self.booking_id} [{self.status}]"

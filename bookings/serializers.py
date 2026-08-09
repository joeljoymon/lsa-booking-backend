from rest_framework import serializers

from .models import LSA, Booking, Parent, Payment


class ParentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Parent
        fields = ["id", "name", "email", "phone", "created_at"]


class LSASerializer(serializers.ModelSerializer):
    # Populated via prefetch_related in the view -> no extra query per row.
    upcoming_booking_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = LSA
        fields = [
            "id",
            "name",
            "email",
            "subject",
            "is_active",
            "upcoming_booking_count",
        ]


class BookingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Booking
        fields = [
            "id",
            "parent",
            "lsa",
            "start_time",
            "end_time",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["status", "created_at", "updated_at"]

    def validate(self, attrs):
        start = attrs.get("start_time")
        end = attrs.get("end_time")
        lsa = attrs.get("lsa")

        if start and end and end <= start:
            raise serializers.ValidationError(
                {"end_time": "end_time must be after start_time."}
            )

        if lsa and start and end:
            overlapping = Booking.objects.filter(
                lsa=lsa,
                status__in=Booking.ACTIVE_STATUSES,
                start_time__lt=end,
                end_time__gt=start,
            )
            # Exclude self when updating an existing booking.
            if self.instance is not None:
                overlapping = overlapping.exclude(pk=self.instance.pk)

            if overlapping.exists():
                raise serializers.ValidationError(
                    "This LSA already has an overlapping session in that time window."
                )

        return attrs


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = [
            "id",
            "booking",
            "reference_id",
            "amount",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["status", "reference_id", "created_at", "updated_at"]


class PaymentWebhookSerializer(serializers.Serializer):
    """
    Payload contract for the payment gateway webhook.

    Expected shape:
    {
        "event": "payment.success" | "payment.failed",
        "reference_id": "<payment.reference_id>"
    }
    """

    EVENT_CHOICES = ("payment.success", "payment.failed")

    event = serializers.ChoiceField(choices=EVENT_CHOICES)
    reference_id = serializers.CharField(max_length=64)

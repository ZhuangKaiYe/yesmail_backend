from rest_framework import serializers
from django.contrib.auth.models import User
from django.contrib.auth import authenticate,get_user_model
from mail.models import Attachment, Email

User = get_user_model()


class AttachmentSerializer(serializers.ModelSerializer):
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = Attachment
        fields = ['id', 'file', 'filename', 'uploaded_at', 'download_url']
        read_only_fields = ['id', 'uploaded_at']

    def get_download_url(self, obj):
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(f'/api/attachments/{obj.id}/download/')
        return f'/api/attachments/{obj.id}/download/'


class RegisterSerializer(serializers.Serializer):
    username = serializers.CharField()
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("Username already exists")
        return value


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        user = authenticate(
            username=data['username'], password=data['password'])
        if user is None:
            raise serializers.ValidationError("Invalid credentials")
        return user


class EmailSerializer(serializers.ModelSerializer):
    sender = serializers.ReadOnlyField(source='from_user.email')
    recipients = serializers.SlugRelatedField(
        many=True,
        slug_field='email', 
        queryset=User.objects.all()
    )
    attachments = AttachmentSerializer(many=True, read_only=True)

    class Meta:
        model = Email
        fields = ['id', 'sender', 'recipients', 'subject',
                  'body', 'sent_at', 'is_read', 'attachments']

    def create(self, validated_data):
        recipients = validated_data.pop('recipients')
        email = Email.objects.create(**validated_data)
        email.recipients.set(recipients)
        return email

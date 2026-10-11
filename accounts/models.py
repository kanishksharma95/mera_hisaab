"""
Custom user model for Mera Hisaab.

Shopkeepers log in with their email (not a username), so we use a custom
``User`` where email is the unique identifier. Defining this in Phase 1 is
important: switching AUTH_USER_MODEL later is very disruptive.
"""
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils.translation import gettext_lazy as _


class UserManager(BaseUserManager):
    """User manager that uses email as the unique identifier."""

    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("An email address is required.")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self._create_user(email, password, **extra_fields)


class User(AbstractUser):
    """Email-first user.

    ``username`` is removed; ``email`` is the login field. ``full_name`` and
    ``phone`` capture the shopkeeper's details collected at registration.
    """

    username = None
    email = models.EmailField(_("email address"), unique=True)
    full_name = models.CharField(_("full name"), max_length=150, blank=True)
    phone = models.CharField(_("phone"), max_length=20, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []  # email + password already required by USERNAME_FIELD

    objects = UserManager()

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")

    def __str__(self):
        return self.full_name or self.email

    def get_short_name(self):
        return self.full_name.split(" ")[0] if self.full_name else self.email


class UserProfile(models.Model):
    """Optional per-user profile details (kept separate from auth fields)."""

    user = models.OneToOneField(
        "accounts.User", on_delete=models.CASCADE, related_name="profile"
    )
    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True)
    preferred_language = models.CharField(
        max_length=8, default="en", choices=[("en", "English"), ("hi", "हिन्दी")]
    )

    def __str__(self):
        return f"Profile<{self.user.email}>"

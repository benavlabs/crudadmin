import logging
from unittest.mock import AsyncMock, patch

import bcrypt
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from crudadmin.core.auth import (
    authenticate_user_by_credentials,
    convert_user_to_dict,
    get_password_hash,
    verify_password,
)


class TestVerifyPassword:
    """Test cases for verify_password function."""

    @pytest.mark.asyncio
    async def test_verify_password_valid_password(self):
        """Test password verification with valid password."""
        plain_password = "test_password_123"
        hashed_password = bcrypt.hashpw(
            plain_password.encode(), bcrypt.gensalt()
        ).decode()

        result = await verify_password(plain_password, hashed_password)
        assert result is True

    @pytest.mark.asyncio
    async def test_verify_password_invalid_password(self):
        """Test password verification with invalid password."""
        plain_password = "test_password_123"
        wrong_password = "wrong_password"
        hashed_password = bcrypt.hashpw(
            plain_password.encode(), bcrypt.gensalt()
        ).decode()

        result = await verify_password(wrong_password, hashed_password)
        assert result is False

    @pytest.mark.asyncio
    async def test_verify_password_empty_plain_password(self):
        """Test password verification with empty plain password."""
        hashed_password = bcrypt.hashpw(b"test", bcrypt.gensalt()).decode()

        result = await verify_password("", hashed_password)
        assert result is False

    @pytest.mark.asyncio
    async def test_verify_password_empty_hashed_password(self):
        """Test password verification with empty hashed password."""
        result = await verify_password("test_password", "")
        assert result is False

    @pytest.mark.asyncio
    async def test_verify_password_invalid_hash_format(self):
        """Test password verification with invalid hash format."""
        result = await verify_password("test_password", "invalid_hash")
        assert result is False

    @pytest.mark.asyncio
    async def test_verify_password_unicode_characters(self):
        """Test password verification with unicode characters."""
        plain_password = "tëst_pàsswörd_123_🔐"
        hashed_password = bcrypt.hashpw(
            plain_password.encode(), bcrypt.gensalt()
        ).decode()

        result = await verify_password(plain_password, hashed_password)
        assert result is True

    @pytest.mark.asyncio
    async def test_verify_password_special_characters(self):
        """Test password verification with special characters."""
        plain_password = "!@#$%^&*()_+-=[]{}|;':\",./<>?"
        hashed_password = bcrypt.hashpw(
            plain_password.encode(), bcrypt.gensalt()
        ).decode()

        result = await verify_password(plain_password, hashed_password)
        assert result is True

    @pytest.mark.asyncio
    async def test_verify_password_exception_handling(self):
        """Test password verification exception handling."""
        with patch("bcrypt.checkpw") as mock_checkpw:
            mock_checkpw.side_effect = Exception("bcrypt error")

            result = await verify_password("test", "test_hash")
            assert result is False

    @pytest.mark.asyncio
    async def test_verify_password_logging_on_error(self, caplog):
        """Test that errors are logged when password verification fails."""
        with patch("bcrypt.checkpw") as mock_checkpw:
            mock_checkpw.side_effect = Exception("bcrypt error")

            with caplog.at_level(logging.ERROR):
                result = await verify_password("test", "test_hash")

            assert result is False
            assert "Error verifying password" in caplog.text
            assert "bcrypt error" in caplog.text


class TestGetPasswordHash:
    """Test cases for get_password_hash function."""

    def test_get_password_hash_valid_password(self):
        """Test password hashing with valid password."""
        password = "test_password_123"
        hashed = get_password_hash(password)

        assert isinstance(hashed, str)
        assert len(hashed) > 0
        assert hashed != password
        assert hashed.startswith("$2b$")

    def test_get_password_hash_empty_password(self):
        """Test password hashing with empty password."""
        hashed = get_password_hash("")

        assert isinstance(hashed, str)
        assert len(hashed) > 0
        assert hashed.startswith("$2b$")

    def test_get_password_hash_unicode_characters(self):
        """Test password hashing with unicode characters."""
        password = "tëst_pàsswörd_123_🔐"
        hashed = get_password_hash(password)

        assert isinstance(hashed, str)
        assert len(hashed) > 0
        assert hashed.startswith("$2b$")

    def test_get_password_hash_special_characters(self):
        """Test password hashing with special characters."""
        password = "!@#$%^&*()_+-=[]{}|;':\",./<>?"
        hashed = get_password_hash(password)

        assert isinstance(hashed, str)
        assert len(hashed) > 0
        assert hashed.startswith("$2b$")

    def test_get_password_hash_consistency(self):
        """Test that same password produces different hashes due to salt."""
        password = "test_password_123"
        hash1 = get_password_hash(password)
        hash2 = get_password_hash(password)

        assert hash1 != hash2
        assert len(hash1) == len(hash2)

    def test_get_password_hash_exception_handling(self):
        """Test password hashing exception handling."""
        with patch("bcrypt.hashpw") as mock_hashpw:
            mock_hashpw.side_effect = Exception("bcrypt error")

            with pytest.raises(Exception, match="bcrypt error"):
                get_password_hash("test_password")

    def test_get_password_hash_logging_on_error(self, caplog):
        """Test that errors are logged when password hashing fails."""
        with patch("bcrypt.hashpw") as mock_hashpw:
            mock_hashpw.side_effect = Exception("bcrypt error")

            with caplog.at_level(logging.ERROR):
                with pytest.raises(Exception):  # noqa: B017
                    get_password_hash("test_password")

            assert "Error hashing password" in caplog.text
            assert "bcrypt error" in caplog.text


class TestConvertUserToDict:
    """Test cases for convert_user_to_dict function."""

    def test_convert_user_to_dict_with_none(self):
        """Test convert_user_to_dict with None input."""
        result = convert_user_to_dict(None)
        assert result is None

    def test_convert_user_to_dict_with_dict(self):
        """Test convert_user_to_dict with dictionary input."""
        user_dict = {
            "id": 1,
            "username": "testuser",
            "email": "test@example.com",
            "hashed_password": "hashed_pass",
            "is_active": True,
            "is_superuser": False,
        }

        result = convert_user_to_dict(user_dict)
        assert result == user_dict

    def test_convert_user_to_dict_with_empty_dict(self):
        """Test convert_user_to_dict with empty dictionary."""
        result = convert_user_to_dict({})
        assert result == {}

    def test_convert_user_to_dict_with_model_object(self):
        """Test convert_user_to_dict with model object."""

        class MockUser:
            def __init__(self):
                self.id = 1
                self.username = "testuser"
                self.email = "test@example.com"
                self.hashed_password = "hashed_pass"
                self.is_active = True
                self.is_superuser = False
                self.created_at = "2023-01-01"
                self.updated_at = "2023-01-01"
                self._private_attr = "should_not_appear"
                self.custom_attr = "should_not_appear"

        mock_user = MockUser()
        result = convert_user_to_dict(mock_user)

        assert result is not None
        assert result["id"] == 1
        assert result["username"] == "testuser"
        assert result["email"] == "test@example.com"
        assert result["hashed_password"] == "hashed_pass"
        assert result["is_active"] is True
        assert result["is_superuser"] is False
        assert result["created_at"] == "2023-01-01"
        assert result["updated_at"] == "2023-01-01"
        assert "_private_attr" not in result
        assert "custom_attr" not in result

    def test_convert_user_to_dict_with_partial_attributes(self):
        """Test convert_user_to_dict with object having only some attributes."""

        class PartialUser:
            def __init__(self):
                self.id = 1
                self.username = "testuser"
                self.email = "test@example.com"
                # Missing other common attributes

        partial_user = PartialUser()
        result = convert_user_to_dict(partial_user)

        assert result is not None
        assert result["id"] == 1
        assert result["username"] == "testuser"
        assert result["email"] == "test@example.com"
        assert "hashed_password" not in result
        assert "is_active" not in result

    def test_convert_user_to_dict_with_none_attributes(self):
        """Test convert_user_to_dict with object having None attributes."""

        class UserWithNone:
            def __init__(self):
                self.id = 1
                self.username = None
                self.email = "test@example.com"
                self.hashed_password = None
                self.is_active = True

        user_with_none = UserWithNone()
        result = convert_user_to_dict(user_with_none)

        assert result is not None
        assert result["id"] == 1
        assert result["username"] is None
        assert result["email"] == "test@example.com"
        assert result["hashed_password"] is None
        assert result["is_active"] is True

    def test_convert_user_to_dict_with_object_without_dict(self):
        """Test convert_user_to_dict with object that doesn't have __dict__."""

        class ObjectWithoutDict:
            __slots__ = ["id", "username"]

            def __init__(self):
                self.id = 1
                self.username = "testuser"

        obj = ObjectWithoutDict()
        result = convert_user_to_dict(obj)

        assert result is None

    def test_convert_user_to_dict_exception_handling(self):
        """Test convert_user_to_dict exception handling."""

        class ProblematicUser:
            def __init__(self):
                self.id = 1
                self.username = "testuser"

            def __getattribute__(self, name):
                if name == "username":
                    raise Exception("Attribute access error")
                return super().__getattribute__(name)

        problematic_user = ProblematicUser()
        result = convert_user_to_dict(problematic_user)

        assert result is None

    def test_convert_user_to_dict_with_primitive_types(self):
        """Test convert_user_to_dict with primitive types."""
        # Test with string
        result = convert_user_to_dict("string")
        assert result is None

        # Test with integer
        result = convert_user_to_dict(123)
        assert result is None

        # Test with list
        result = convert_user_to_dict([1, 2, 3])
        assert result is None


class TestAuthenticateUserByCredentials:
    """Test cases for authenticate_user_by_credentials function."""

    @pytest.mark.asyncio
    async def test_authenticate_user_by_credentials_email_success(self):
        """Test successful authentication with email."""
        email = "test@example.com"
        password = "test_password"
        hashed_password = get_password_hash(password)

        mock_user = {
            "id": 1,
            "username": "testuser",
            "email": email,
            "hashed_password": hashed_password,
            "is_active": True,
        }

        mock_db = AsyncMock(spec=AsyncSession)
        mock_crud_users = AsyncMock()
        mock_crud_users.get.return_value = mock_user

        result = await authenticate_user_by_credentials(
            username_or_email=email,
            password=password,
            db=mock_db,
            crud_users=mock_crud_users,
        )

        assert result is not None
        assert result["id"] == 1
        assert result["username"] == "testuser"
        assert result["email"] == email
        mock_crud_users.get.assert_called_once_with(db=mock_db, email=email)

    @pytest.mark.asyncio
    async def test_authenticate_user_by_credentials_username_success(self):
        """Test successful authentication with username."""
        username = "testuser"
        password = "test_password"
        hashed_password = get_password_hash(password)

        mock_user = {
            "id": 1,
            "username": username,
            "email": "test@example.com",
            "hashed_password": hashed_password,
            "is_active": True,
        }

        mock_db = AsyncMock(spec=AsyncSession)
        mock_crud_users = AsyncMock()
        mock_crud_users.get.return_value = mock_user

        result = await authenticate_user_by_credentials(
            username_or_email=username,
            password=password,
            db=mock_db,
            crud_users=mock_crud_users,
        )

        assert result is not None
        assert result["id"] == 1
        assert result["username"] == username
        mock_crud_users.get.assert_called_once_with(db=mock_db, username=username)

    @pytest.mark.asyncio
    async def test_authenticate_user_by_credentials_model_object(self):
        """Test authentication with model object returned from CRUD."""

        class MockUser:
            def __init__(self):
                self.id = 1
                self.username = "testuser"
                self.email = "test@example.com"
                self.hashed_password = get_password_hash("test_password")
                self.is_active = True
                self.is_superuser = False
                self.created_at = "2023-01-01"
                self.updated_at = "2023-01-01"

        mock_user_obj = MockUser()
        mock_db = AsyncMock(spec=AsyncSession)
        mock_crud_users = AsyncMock()
        mock_crud_users.get.return_value = mock_user_obj

        result = await authenticate_user_by_credentials(
            username_or_email="testuser",
            password="test_password",
            db=mock_db,
            crud_users=mock_crud_users,
        )

        assert result is not None
        assert result["id"] == 1
        assert result["username"] == "testuser"
        assert result["email"] == "test@example.com"

    @pytest.mark.asyncio
    async def test_authenticate_user_by_credentials_user_not_found(self):
        """Test authentication when user is not found."""
        mock_db = AsyncMock(spec=AsyncSession)
        mock_crud_users = AsyncMock()
        mock_crud_users.get.return_value = None

        result = await authenticate_user_by_credentials(
            username_or_email="nonexistent@example.com",
            password="test_password",
            db=mock_db,
            crud_users=mock_crud_users,
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_authenticate_user_by_credentials_wrong_password(self):
        """Test authentication with wrong password."""
        mock_user = {
            "id": 1,
            "username": "testuser",
            "email": "test@example.com",
            "hashed_password": get_password_hash("correct_password"),
            "is_active": True,
        }

        mock_db = AsyncMock(spec=AsyncSession)
        mock_crud_users = AsyncMock()
        mock_crud_users.get.return_value = mock_user

        result = await authenticate_user_by_credentials(
            username_or_email="test@example.com",
            password="wrong_password",
            db=mock_db,
            crud_users=mock_crud_users,
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_authenticate_user_by_credentials_no_hashed_password(self):
        """Test authentication when user has no hashed password."""
        mock_user = {
            "id": 1,
            "username": "testuser",
            "email": "test@example.com",
            "is_active": True,
        }

        mock_db = AsyncMock(spec=AsyncSession)
        mock_crud_users = AsyncMock()
        mock_crud_users.get.return_value = mock_user

        result = await authenticate_user_by_credentials(
            username_or_email="test@example.com",
            password="test_password",
            db=mock_db,
            crud_users=mock_crud_users,
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_authenticate_user_by_credentials_empty_credentials(self):
        """Test authentication with empty credentials."""
        mock_db = AsyncMock(spec=AsyncSession)
        mock_crud_users = AsyncMock()
        mock_crud_users.get.return_value = None

        result = await authenticate_user_by_credentials(
            username_or_email="",
            password="",
            db=mock_db,
            crud_users=mock_crud_users,
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_authenticate_user_by_credentials_unicode_credentials(self):
        """Test authentication with unicode credentials."""
        username = "tëstüsér"
        password = "tëst_pàsswörd_🔐"
        hashed_password = get_password_hash(password)

        mock_user = {
            "id": 1,
            "username": username,
            "email": "test@example.com",
            "hashed_password": hashed_password,
            "is_active": True,
        }

        mock_db = AsyncMock(spec=AsyncSession)
        mock_crud_users = AsyncMock()
        mock_crud_users.get.return_value = mock_user

        result = await authenticate_user_by_credentials(
            username_or_email=username,
            password=password,
            db=mock_db,
            crud_users=mock_crud_users,
        )

        assert result is not None
        assert result["username"] == username

    @pytest.mark.asyncio
    async def test_authenticate_user_by_credentials_exception_handling(self):
        """Test authentication exception handling."""
        mock_db = AsyncMock(spec=AsyncSession)
        mock_crud_users = AsyncMock()
        mock_crud_users.get.side_effect = Exception("Database error")

        result = await authenticate_user_by_credentials(
            username_or_email="test@example.com",
            password="test_password",
            db=mock_db,
            crud_users=mock_crud_users,
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_authenticate_user_by_credentials_logging_debug(self, caplog):
        """Test debug logging during authentication."""
        mock_db = AsyncMock(spec=AsyncSession)
        mock_crud_users = AsyncMock()
        mock_crud_users.get.return_value = None

        with caplog.at_level(logging.DEBUG):
            result = await authenticate_user_by_credentials(
                username_or_email="test@example.com",
                password="test_password",
                db=mock_db,
                crud_users=mock_crud_users,
            )

        assert result is None
        assert "Attempting to authenticate user" in caplog.text
        assert "User not found in database" in caplog.text

    @pytest.mark.asyncio
    async def test_authenticate_user_by_credentials_convert_user_fails(self):
        """Test authentication when convert_user_to_dict fails."""

        # Create a user object that will fail conversion but allow basic operations
        class ProblematicUser:
            def __init__(self):
                self._allow_basic_ops = True

            def __getattribute__(self, name):
                # Allow basic operations needed for mocking
                if name in ["_allow_basic_ops", "__class__", "__dict__", "__module__"]:
                    return object.__getattribute__(self, name)
                # Fail for the attributes that convert_user_to_dict will try to access
                if name in [
                    "id",
                    "username",
                    "email",
                    "hashed_password",
                    "is_active",
                    "is_superuser",
                    "created_at",
                    "updated_at",
                ]:
                    raise Exception("Attribute access error")
                return object.__getattribute__(self, name)

        problematic_user = ProblematicUser()
        mock_db = AsyncMock(spec=AsyncSession)
        mock_crud_users = AsyncMock()
        mock_crud_users.get.return_value = problematic_user

        result = await authenticate_user_by_credentials(
            username_or_email="test@example.com",
            password="test_password",
            db=mock_db,
            crud_users=mock_crud_users,
        )

        assert result is None

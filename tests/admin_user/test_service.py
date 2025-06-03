from unittest.mock import ANY, AsyncMock, patch

import bcrypt
import pytest

from crudadmin.admin_user.schemas import AdminUser
from crudadmin.admin_user.service import AdminUserService
from crudadmin.core.auth import convert_user_to_dict


@pytest.mark.asyncio
async def test_admin_user_service_initialization(db_config):
    """Test AdminUserService initialization."""
    service = AdminUserService(db_config)

    assert service.db_config == db_config
    assert service.crud_users == db_config.crud_users


@pytest.mark.asyncio
async def test_verify_password(admin_user_service):
    """Test password verification."""
    plain_password = "test_password_123"
    hashed_password = admin_user_service.get_password_hash(plain_password)

    # Test correct password
    is_valid = await admin_user_service.verify_password(plain_password, hashed_password)
    assert is_valid is True

    # Test incorrect password
    is_invalid = await admin_user_service.verify_password(
        "wrong_password", hashed_password
    )
    assert is_invalid is False


def test_get_password_hash(admin_user_service):
    """Test password hashing."""
    password = "test_password_123"
    hashed = admin_user_service.get_password_hash(password)

    assert isinstance(hashed, str)
    assert len(hashed) > 0
    assert hashed != password

    # Verify the hash can be used with bcrypt
    assert bcrypt.checkpw(password.encode(), hashed.encode())


@pytest.mark.asyncio
async def test_authenticate_user_by_username_success(admin_user_service, db_config):
    """Test successful user authentication by username."""
    username = "testuser"
    password = "test_password_123"
    hashed_password = admin_user_service.get_password_hash(password)

    mock_user = {
        "id": 1,
        "username": username,
        "hashed_password": hashed_password,
    }

    with patch.object(
        admin_user_service.crud_users, "get", new_callable=AsyncMock
    ) as mock_get:
        mock_get.return_value = mock_user

        result = await admin_user_service.authenticate_user(
            username, password, AsyncMock()
        )

        assert result is not False
        assert result["username"] == username
        assert result["id"] == 1
        mock_get.assert_called_once_with(db=ANY, username=username)


@pytest.mark.asyncio
async def test_authenticate_user_by_email_success(admin_user_service, db_config):
    """Test successful user authentication by email."""
    email = "test@example.com"
    password = "test_password_123"
    hashed_password = admin_user_service.get_password_hash(password)

    mock_user = {
        "id": 1,
        "username": "testuser",
        "hashed_password": hashed_password,
    }

    with patch.object(
        admin_user_service.crud_users, "get", new_callable=AsyncMock
    ) as mock_get:
        mock_get.return_value = mock_user

        result = await admin_user_service.authenticate_user(
            email, password, AsyncMock()
        )

        assert result is not False
        assert result["username"] == "testuser"
        assert result["id"] == 1
        mock_get.assert_called_once_with(db=ANY, email=email)


@pytest.mark.asyncio
async def test_authenticate_user_not_found(admin_user_service):
    """Test authentication when user is not found."""
    with patch.object(
        admin_user_service.crud_users, "get", new_callable=AsyncMock
    ) as mock_get:
        mock_get.return_value = None

        result = await admin_user_service.authenticate_user(
            "nonexistent", "password", AsyncMock()
        )

        assert result is False


@pytest.mark.asyncio
async def test_authenticate_user_wrong_password(admin_user_service):
    """Test authentication with wrong password."""
    username = "testuser"
    correct_password = "correct_password"
    wrong_password = "wrong_password"
    hashed_password = admin_user_service.get_password_hash(correct_password)

    mock_user = {
        "id": 1,
        "username": username,
        "hashed_password": hashed_password,
    }

    with patch.object(
        admin_user_service.crud_users, "get", new_callable=AsyncMock
    ) as mock_get:
        mock_get.return_value = mock_user

        result = await admin_user_service.authenticate_user(
            username, wrong_password, AsyncMock()
        )

        assert result is False


@pytest.mark.asyncio
async def test_authenticate_user_no_hashed_password(admin_user_service):
    """Test authentication when user has no hashed password."""
    mock_user = {
        "id": 1,
        "username": "testuser",
        # Missing hashed_password
    }

    with patch.object(
        admin_user_service.crud_users, "get", new_callable=AsyncMock
    ) as mock_get:
        mock_get.return_value = mock_user

        result = await admin_user_service.authenticate_user(
            "testuser", "password", AsyncMock()
        )

        assert result is False


@pytest.mark.asyncio
async def test_authenticate_user_exception_handling(admin_user_service):
    """Test authentication exception handling."""
    with patch.object(
        admin_user_service.crud_users, "get", new_callable=AsyncMock
    ) as mock_get:
        mock_get.side_effect = Exception("Database error")

        result = await admin_user_service.authenticate_user(
            "testuser", "password", AsyncMock()
        )

        assert result is False


@pytest.mark.asyncio
async def test_create_first_admin_new_user(admin_user_service):
    """Test creating first admin user when user doesn't exist."""
    username = "admin"
    password = "admin_password_123"

    create_first_admin_func = admin_user_service.create_first_admin()

    with patch.object(
        admin_user_service.crud_users, "exists", new_callable=AsyncMock
    ) as mock_exists, patch.object(
        admin_user_service.crud_users, "create", new_callable=AsyncMock
    ) as mock_create:
        mock_exists.return_value = False
        mock_create.return_value = {
            "id": 1,
            "username": username,
            "hashed_password": "hashed_password",
        }

        result = await create_first_admin_func(username, password, AsyncMock())

        assert result is not None
        assert result["username"] == username
        mock_exists.assert_called_once()
        mock_create.assert_called_once()


@pytest.mark.asyncio
async def test_create_first_admin_existing_user(admin_user_service):
    """Test creating first admin user when user already exists."""
    username = "admin"
    password = "admin_password_123"

    create_first_admin_func = admin_user_service.create_first_admin()

    with patch.object(
        admin_user_service.crud_users, "exists", new_callable=AsyncMock
    ) as mock_exists:
        mock_exists.return_value = True

        result = await create_first_admin_func(username, password, AsyncMock())

        assert result is None
        mock_exists.assert_called_once()


def test_convert_user_to_dict_with_none():
    """Test _convert_user_to_dict with None input."""
    result = convert_user_to_dict(None)
    assert result is None


def test_convert_user_to_dict_with_dict():
    """Test _convert_user_to_dict with dict input."""
    user_dict = {"id": 1, "username": "test", "hashed_password": "hash"}
    result = convert_user_to_dict(user_dict)
    assert result == user_dict


def test_convert_user_to_dict_with_admin_user():
    """Test _convert_user_to_dict with AdminUser model."""
    from unittest.mock import Mock

    admin_user = Mock(spec=AdminUser)
    admin_user.id = 1
    admin_user.username = "test"
    admin_user.hashed_password = "hash"

    result = convert_user_to_dict(admin_user)

    assert result == {
        "id": 1,
        "username": "test",
        "hashed_password": "hash",
    }


def test_convert_user_to_dict_with_unknown_type():
    """Test _convert_user_to_dict with unknown type."""
    result = convert_user_to_dict("unknown_type")
    assert result is None


@pytest.mark.asyncio
async def test_authenticate_user_with_admin_user_model(admin_user_service):
    """Test authentication when crud returns AdminUser model."""
    from unittest.mock import Mock

    username = "testuser"
    password = "test_password_123"
    hashed_password = admin_user_service.get_password_hash(password)

    mock_user = Mock(spec=AdminUser)
    mock_user.id = 1
    mock_user.username = username
    mock_user.hashed_password = hashed_password

    with patch.object(
        admin_user_service.crud_users, "get", new_callable=AsyncMock
    ) as mock_get:
        mock_get.return_value = mock_user

        result = await admin_user_service.authenticate_user(
            username, password, AsyncMock()
        )

        assert result is not False
        assert result["username"] == username
        assert result["id"] == 1


@pytest.mark.asyncio
async def test_password_hashing_consistency(admin_user_service):
    """Test that password hashing is consistent and secure."""
    password = "test_password_123"

    # Generate multiple hashes of the same password
    hash1 = admin_user_service.get_password_hash(password)
    hash2 = admin_user_service.get_password_hash(password)

    # Hashes should be different (due to salt)
    assert hash1 != hash2

    # But both should verify correctly
    assert await admin_user_service.verify_password(password, hash1)
    assert await admin_user_service.verify_password(password, hash2)


@pytest.mark.asyncio
async def test_authenticate_user_email_detection(admin_user_service):
    """Test that email vs username is correctly detected."""
    email = "user@example.com"
    username = "username"
    password = "password"

    with patch.object(
        admin_user_service.crud_users, "get", new_callable=AsyncMock
    ) as mock_get:
        mock_get.return_value = None

        # Test email detection
        await admin_user_service.authenticate_user(email, password, AsyncMock())
        mock_get.assert_called_with(db=ANY, email=email)

        mock_get.reset_mock()

        # Test username detection
        await admin_user_service.authenticate_user(username, password, AsyncMock())
        mock_get.assert_called_with(db=ANY, username=username)

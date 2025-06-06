# Managing Admin Users

This guide covers how to create, manage, and configure admin user accounts for accessing your CRUDAdmin interface. You'll learn about user creation, editing user details, understanding permissions, and following security best practices.

## Prerequisites

Before managing admin users, ensure you have:

- A configured CRUDAdmin instance (see [Basic Configuration](configuration.md))
- Access to your admin interface (typically at `/admin`)
- Understanding of password security requirements

---

## Creating Admin Users

### Automatic Creation (Initial Admin)

The easiest way to create your first admin user is during CRUDAdmin initialization:

```python
# Create admin interface with initial admin user
admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY=os.environ["ADMIN_SECRET_KEY"],
    initial_admin={
        "username": "admin",
        "password": "SecurePassword123!"
    }
)
```

**How it works:**

- Only creates the admin user if no admin users exist
- Password is automatically hashed using bcrypt
- User is created with superuser privileges
- Runs during `admin.initialize()` or at startup

### Manual Creation via Admin Interface

Once you have access to the admin interface:

1. **Navigate to Admin Users**: Go to `/admin/AdminUser`
2. **Click "Add AdminUser"**: Use the create button
3. **Fill the form**:
    - **Username**: 2-20 characters, lowercase letters and numbers only (`a-z0-9`)
    - **Password**: Minimum 8 characters with letters, numbers, and special characters
4. **Submit**: User is created with superuser privileges

### Creation via Code

For programmatic user creation:

```python
from crudadmin.admin_user.schemas import AdminUserCreate

async def create_admin_user(username: str, password: str):
    # Create the user data
    user_data = AdminUserCreate(
        username=username,
        password=password  # Will be hashed automatically
    )
    
    # Get admin database session
    async for admin_session in admin.db_config.get_admin_db():
        try:
            # Create user using the admin user service
            hashed_password = admin.admin_user_service.get_password_hash(password)
            internal_data = AdminUserCreateInternal(
                username=username,
                hashed_password=hashed_password,
            )
            
            await admin.db_config.crud_users.create(
                admin_session, object=internal_data
            )
            await admin_session.commit()
            print(f"Created admin user: {username}")
            
        except Exception as e:
            print(f"Error creating user: {e}")
            await admin_session.rollback()

# Usage
await create_admin_user("manager", "SecurePass456!")
```

---

## User Requirements and Validation

### Username Requirements

Admin usernames must follow specific rules:

```python
# ✅ Valid usernames
"admin"      # Basic admin
"user123"    # Numbers allowed
"manager2"   # Alphanumeric

# ❌ Invalid usernames
"Admin"      # No uppercase letters
"user-name"  # No hyphens
"user_name"  # No underscores
"ab"         # Too short (minimum 2 characters)
"verylongusernamethatexceedslimit"  # Too long (maximum 20 characters)
```

**Pattern**: `^[a-z0-9]+$` (lowercase letters and numbers only)

### Password Requirements

Passwords must meet security standards:

```python
# ✅ Valid passwords
"SecurePass123!"    # Letters, numbers, special chars
"MyPassword2024#"   # Mixed case, numbers, symbols
"admin@2024!pass"   # Complex combination

# ❌ Invalid passwords
"simple"           # Too short (minimum 8 characters)
"password"         # No numbers or special characters
"12345678"         # Only numbers
"UPPERCASE"        # No lowercase or numbers
```

**Requirements**:

- Minimum 8 characters
- Must contain letters, numbers, or special characters
- Pattern validation: `^.{8,}|[0-9]+|[A-Z]+|[a-z]+|[^a-zA-Z0-9]+$`

---

## Managing Existing Users

### Viewing Admin Users

To see all admin users:

1. **Access AdminUser section**: Navigate to `/admin/AdminUser`
2. **View user list**: See all admin accounts with:
    - Username
    - Creation date
    - Last updated date
    - Superuser status

### Editing User Details

To modify an existing admin user:

1. **Select user**: Check the box next to the user in the list
2. **Click "Update"**: Opens the edit form
3. **Modify fields**:
    - **Username**: Change if needed (subject to validation rules)
    - **Password**: Leave blank to keep current password, or enter new password
4. **Save changes**: Submit the form

**Code example for programmatic updates:**

```python
from crudadmin.admin_user.schemas import AdminUserUpdate

async def update_admin_user(
    user_id: int,
    new_password: str = None,
    new_username: str = None
):
    # Prepare update data (only include fields that are changing)
    update_data = {}
    if new_username:
        update_data["username"] = new_username
    if new_password:
        update_data["password"] = new_password  # Will be hashed automatically
    
    if not update_data:
        print("No changes to make")
        return
    
    user_update = AdminUserUpdate(**update_data)
    
    async for admin_session in admin.db_config.get_admin_db():
        try:
            await admin.db_config.crud_users.update(
                admin_session, 
                object=user_update, 
                id=user_id
            )
            await admin_session.commit()
            print(f"Updated user ID {user_id}")
            
        except Exception as e:
            print(f"Error updating user: {e}")
            await admin_session.rollback()

# Usage
await update_admin_user(user_id=1, new_password="NewSecurePass789!")
```

### Password Changes

When changing passwords:

1. **Via Interface**: Enter new password in the password field during edit
2. **Via Code**: Use the update method with a new password
3. **Security**: Old password is completely replaced (no password history)

**Important Notes:**

- Passwords are automatically hashed using bcrypt
- Empty password field during update means "no change"
- New password must meet all validation requirements

---

## User Permissions and Access Control

### Superuser Status

All admin users in CRUDAdmin have superuser privileges by default:

```python
# User model structure
class AdminUser:
    id: int
    username: str
    hashed_password: str
    created_at: datetime
    updated_at: Optional[datetime]
    is_superuser: bool = True  # Always True for admin users
```

**What superuser means:**
- Full access to all admin interface features
- Can view, create, update, and delete all records
- Access to management features (health checks, event logs)
- Can manage other admin users

### Available Actions

Admin users can perform these actions in the interface:

| Action | AdminUser | AdminSession | Your Models |
|--------|-----------|--------------|-------------|
| **View** | ✅ | ✅ | ✅* |
| **Create** | ✅ | ❌ | ✅* |
| **Update** | ✅ | ❌ | ✅* |
| **Delete** | ❌ | ✅ | ✅* |

**Notes:**

- `*` = Depends on `allowed_actions` configuration for your models
- AdminUser deletion is disabled to prevent accidental lockouts
- AdminSessions can be deleted to force logout

### Session Management

Each admin user can have multiple concurrent sessions:

```python
# Configure session limits (in CRUDAdmin initialization)
admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY=key,
    max_sessions_per_user=3,        # Limit concurrent sessions
    session_timeout_minutes=30,     # Auto-logout after inactivity
    cleanup_interval_minutes=15,    # How often to clean expired sessions
)
```

**Session behavior:**

- Each login creates a new session
- Sessions expire after inactivity timeout
- Exceeding max sessions removes oldest session
- Sessions can be viewed/deleted in AdminSession section

---

## Security Best Practices

### Environment-Based User Management

```python
# Development: Simple auto-admin
admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY="dev-key-change-in-production",
    initial_admin={
        "username": "admin",
        "password": "admin123"  # Simple for development
    }
)

# Production: No auto-admin, manual creation
admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY=os.environ["ADMIN_SECRET_KEY"],
    initial_admin=None  # Create admin users manually
)
```

### Strong Password Policies

Implement additional password checks:

```python
import re

def validate_strong_password(password: str) -> bool:
    """Enhanced password validation"""
    checks = [
        len(password) >= 12,  # Longer minimum
        re.search(r'[A-Z]', password),  # Uppercase letter
        re.search(r'[a-z]', password),  # Lowercase letter
        re.search(r'\d', password),     # Number
        re.search(r'[!@#$%^&*(),.?":{}|<>]', password),  # Special char
        password != password.lower(),   # Mixed case
        password != password.upper(),   # Mixed case
    ]
    return all(checks)

# Use in your application
def create_secure_admin(username: str, password: str):
    if not validate_strong_password(password):
        raise ValueError("Password does not meet security requirements")
    
    # Create user...
```

### Regular User Auditing

Monitor and audit admin users:

```python
async def audit_admin_users():
    """List all admin users with their last activity"""
    async for admin_session in admin.db_config.get_admin_db():
        # Get all admin users
        users = await admin.db_config.crud_users.get_multi(admin_session)
        
        print("Admin Users Audit:")
        print("-" * 50)
        for user in users:
            print(f"Username: {user.username}")
            print(f"Created: {user.created_at}")
            print(f"Updated: {user.updated_at}")
            print(f"Superuser: {user.is_superuser}")
            print("-" * 30)

# Run periodically
await audit_admin_users()
```

### Session Security

Monitor active sessions:

```python
async def check_active_sessions():
    """Review active admin sessions"""
    async for admin_session in admin.db_config.get_admin_db():
        sessions = await admin.db_config.crud_sessions.get_multi(admin_session)
        
        print("Active Sessions:")
        print("-" * 40)
        for session in sessions:
            print(f"User: {session.user_id}")
            print(f"Created: {session.created_at}")
            print(f"Expires: {session.expires_at}")
            print("-" * 20)

await check_active_sessions()
```

---

## Common Tasks

### Resetting a User Password

```python
async def reset_user_password(username: str, new_password: str):
    """Reset password for a specific user"""
    if not validate_strong_password(new_password):
        raise ValueError("New password does not meet requirements")
    
    async for admin_session in admin.db_config.get_admin_db():
        try:
            # Find user by username
            user = await admin.db_config.crud_users.get(
                admin_session, 
                username=username
            )
            
            if not user:
                print(f"User '{username}' not found")
                return
            
            # Update password
            update_data = AdminUserUpdate(password=new_password)
            await admin.db_config.crud_users.update(
                admin_session,
                object=update_data,
                id=user.id
            )
            await admin_session.commit()
            print(f"Password reset for user '{username}'")
            
        except Exception as e:
            print(f"Error resetting password: {e}")
            await admin_session.rollback()

# Usage
await reset_user_password("admin", "NewSecurePassword123!")
```

### Disabling a User (Workaround)

Since there's no built-in disable feature, you can change their password:

```python
async def disable_user(username: str):
    """Effectively disable a user by setting an unusable password"""
    import secrets
    
    # Set a random, unknown password
    random_password = secrets.token_urlsafe(32)
    await reset_user_password(username, random_password)
    print(f"User '{username}' has been effectively disabled")
    print("Store this password securely if you need to re-enable:")
    print(f"Password: {random_password}")

# Usage
await disable_user("oldadmin")
```

### Force Logout (Session Termination)

```python
async def force_user_logout(username: str):
    """Terminate all sessions for a specific user"""
    async for admin_session in admin.db_config.get_admin_db():
        try:
            # Get user
            user = await admin.db_config.crud_users.get(
                admin_session,
                username=username
            )
            
            if not user:
                print(f"User '{username}' not found")
                return
            
            # Delete all sessions for this user
            await admin.db_config.crud_sessions.delete(
                admin_session,
                user_id=user.id
            )
            await admin_session.commit()
            print(f"All sessions terminated for user '{username}'")
            
        except Exception as e:
            print(f"Error terminating sessions: {e}")
            await admin_session.rollback()

# Usage
await force_user_logout("admin")
```

---

## Next Steps

After setting up admin users:

1. **[Learn the Interface](interface.md)** to effectively navigate and use the admin panel
2. **[Add Models](adding-models.md)** to manage your application data
3. Explore **[Advanced Topics](../advanced/overview.md)** for production-level user management and security features 
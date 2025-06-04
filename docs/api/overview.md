# API Reference Overview

Welcome to the API Reference section of CRUDAdmin documentation. This section provides detailed information about the various classes, functions, and modules that make up our modern admin interface for FastAPI applications. Whether you are looking to extend the admin interface, integrate with your existing systems, or explore advanced configuration options, this section will guide you through the intricacies of our codebase.

## Key Components

CRUDAdmin's API is comprised of several key components, each serving a specific purpose in creating a comprehensive admin interface:

1. **CRUDAdmin Class**: The main entry point and core class for creating admin interfaces. It handles the creation of the admin application, model registration, authentication setup, and security configuration.

    - [CRUDAdmin Class Reference](crud_admin.md)

2. **ModelView Class**: Handles the representation and CRUD operations for individual SQLAlchemy models within the admin interface. It provides customizable views with filtering, pagination, and bulk operations.

    - [ModelView Class Reference](model_view.md)

3. **AdminSite Class**: The foundation class that manages the overall admin site structure, routing, and template rendering. It coordinates between different model views and handles the main admin interface.

    - [AdminSite Class Reference](admin_site.md)

4. **Session Management System**: A comprehensive session management system with multiple backend options (Memory, Redis, Memcached, Database, Hybrid) providing secure authentication, CSRF protection, and session tracking.

    - [Session Management API Reference](session.md)

5. **Event System**: A robust event logging and audit trail system that tracks all admin actions, authentication events, and security-related activities with comprehensive audit capabilities.

    - [Event System API Reference](events.md)

## Architecture Overview

CRUDAdmin follows a modular architecture designed for flexibility and scalability:

### Core Layer
- **Authentication & Authorization**: Secure admin user management with role-based access
- **Session Management**: Multi-backend session storage with security features
- **Rate Limiting**: Protection against abuse and brute force attacks
- **Database Integration**: SQLAlchemy model integration with FastCRUD backend

### Interface Layer
- **Admin Site**: Main admin interface coordination and routing
- **Model Views**: Individual model CRUD interfaces with customization options
- **Template System**: HTMX-powered responsive UI with modern design
- **Static Assets**: CSS, JavaScript, and image resources

### Event Layer
- **Event Logging**: Comprehensive audit trail for all admin actions
- **Security Events**: Authentication and authorization event tracking
- **Audit Integration**: Automated logging with decorator support

## Usage Patterns

Each component is documented with its own dedicated page, where you can find detailed information about its methods, parameters, return types, and usage examples. These pages are designed to provide you with all the information you need to understand and work with our API effectively.

## Contribution

If you wish to contribute to the development of CRUDAdmin, please refer to our [Contributing Guidelines](../community/CONTRIBUTING.md). We welcome contributions of all forms, from bug fixes to feature development and documentation improvements.

## Support & Feedback

Your feedback is crucial in helping us improve this documentation and the CRUDAdmin library. If you have any suggestions, corrections, or queries, please:

- Open an issue on our [GitHub repository](https://github.com/benavlabs/crudadmin)
- Join our community discussions
- Contribute to the documentation

---

Navigate through each section for detailed documentation of our API components. Each page includes comprehensive examples, parameter descriptions, and usage patterns to help you make the most of CRUDAdmin's capabilities.

# Usage Overview

This section guides you through everything you need to know about using CRUDAdmin effectively in your projects. Follow these topics in order for the best learning experience.

## Getting Started

### 1. [Basic Configuration](configuration.md)
Learn how to set up and configure your CRUDAdmin instance for different environments.

- **Creating your first admin interface** with essential settings
- **Session backend configuration** (Memory, Redis, Memcached, Database, Hybrid)
- **Security settings** for authentication and access control
- **Environment-based configuration** for development vs production
- **FastAPI integration** patterns and best practices

### 2. [Adding Models](adding-models.md)
Master the core functionality of registering your SQLAlchemy models with CRUDAdmin.

- **Model registration** with create, update, and read schemas
- **Action control** (view, create, update, delete permissions)
- **Password field handling** with automatic transformation
- **Advanced schema configuration** for different operations
- **Real-world examples** and troubleshooting tips

### 3. [Managing Admin Users](admin-users.md)
Set up authentication and manage who can access your admin interface.

- **Creating admin users** and managing credentials
- **Authentication flow** and session management
- **User roles and permissions** (if applicable)
- **Security best practices** for admin access

### 4. [Using the Interface](interface.md)
Navigate and operate the admin interface effectively for daily tasks.

- **Dashboard navigation** and understanding the layout
- **CRUD operations** (Create, Read, Update, Delete)
- **Search and filtering** data efficiently
- **Bulk operations** for managing multiple records
- **Form handling** and validation

### 5. [Common Patterns](common-patterns.md)
Real-world usage patterns and scenarios you'll encounter in practice.

- **Multi-model relationships** (blog systems, e-commerce catalogs)
- **Role-based access patterns** for different admin levels
- **Advanced validation patterns** with business logic
- **Performance optimization** for large datasets
- **Integration patterns** with existing FastAPI applications
- **Security patterns** for production environments

## What's Next?

After completing the Usage section, you'll have a solid foundation for building and managing admin interfaces with CRUDAdmin. From here, you can explore:

- **[Advanced Features](../advanced/overview.md)** - Production-grade features like event tracking, advanced session management, and security
- **[API Reference](../api/overview.md)** - Detailed technical documentation for all classes and methods
- **[Community](../community/overview.md)** - Contributing guidelines and getting help

## Quick Navigation

Need to jump to a specific topic? Here are the most commonly accessed sections:

- **[Quick setup example](configuration.md#basic-example)** - Get running in 5 minutes
- **[Adding your first model](adding-models.md#basic-model-registration)** - Register a model and start managing data
- **[Search and filtering](interface.md#search-and-filtering)** - Find records quickly
- **[Performance tips](common-patterns.md#performance-optimization-patterns)** - Optimize for large datasets
- **[Security setup](common-patterns.md#security-patterns)** - Production security configuration 
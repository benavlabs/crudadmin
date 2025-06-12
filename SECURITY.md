# Security Policy

## Supported Versions

CRUDAdmin is currently in pre-1.0.0 development. During this phase, only the latest version receives security updates and patches.

| Version        | Supported          |
| -------------- | ------------------ |
| Latest Release | :white_check_mark: |
| Older Versions | :x:                |

We strongly recommend always using the latest version of CRUDAdmin to ensure you have all security fixes and improvements.

## Reporting a Vulnerability

We take the security of CRUDAdmin seriously. If you believe you have found a security vulnerability, please report it to us as described below.

### Reporting Process

1. **Do Not** disclose the vulnerability publicly until it has been addressed by our team
2. Submit the vulnerability report through one of these channels:

   - Email: igor.magalhaes.r+crudadmin@gmail.com
   - GitHub Security Advisory: https://github.com/igorbenav/crudadmin/security/advisories/new

### What to Include

Please provide detailed information about the vulnerability, including:

- A clear description of the vulnerability
- Steps to reproduce the issue
- Potential impact
- Suggested fix (if available)
- Your contact information for follow-up questions

### Response Timeline

- Initial Response: Within 48 hours
- Status Update: Within 1 week
- Fix Timeline: Based on severity
  - Critical: Within 7 days
  - High: Within 14 days
  - Medium: Within 30 days
  - Low: Within 60 days

### What to Expect

1. **Acknowledgment**: You will receive an acknowledgment of your report within 48 hours
2. **Investigation**: Our team will investigate the issue and determine its impact
3. **Updates**: You will receive updates on the status of your report
4. **Resolution**: Once resolved, you will be notified of the fix
5. **Public Disclosure**: Coordinated disclosure after the fix is released

## Security Considerations

### Database Security

CRUDAdmin provides robust authentication and session management. When using CRUDAdmin, ensure:

1. Use strong session backends (Redis recommended for production)
2. Configure appropriate session timeouts and limits
3. Enable secure cookies and HTTPS enforcement
4. Implement proper password policies
5. Monitor and audit admin user activities

### Access Control and IP Restrictions

CRUDAdmin includes built-in access control features. When configuring access:

1. Define allowed IP addresses and networks
2. Implement proper authorization checks
3. Use HTTPS for all admin communications
4. Configure rate limiting for login attempts
5. Monitor and log access attempts

### Data Protection and Privacy

1. Never expose sensitive data in error messages
2. Implement proper logging practices
3. Use HTTPS for all admin communications
4. Follow data protection regulations (GDPR, CCPA, etc.)
5. Implement proper data encryption at rest

## Best Practices

1. **Always use the latest supported version**
2. Use Redis or Memcached for session management in production
3. Enable HTTPS enforcement and secure cookies
4. Regularly update dependencies
5. Follow the principle of least privilege
6. Implement proper error handling
7. Use secure configuration management
8. Regular security audits and testing

## Security Features

CRUDAdmin includes several security features:

1. **Multi-Backend Session Management**: Memory, Redis, Memcached, Database, and Hybrid backends
2. **Built-in Security**: CSRF protection, rate limiting, IP restrictions, HTTPS enforcement
3. **Session Security**: Automatic expiration, concurrent session limits, device tracking
4. **Access Control**: IP-based restrictions, network-based access control
5. **Event Tracking**: Comprehensive audit trails for all admin actions

## Disclaimer

While CRUDAdmin implements security best practices, it's crucial to properly secure your application as a whole. This includes:

1. Proper session backend configuration
2. Secure environment variable management
3. Monitoring and logging
4. Proper database security
5. Network security measures
6. Regular security updates and audits

## Updates and Notifications

Stay informed about security updates:

1. Watch the GitHub repository
2. Follow our security announcements
3. Subscribe to our security mailing list
4. Monitor our release notes

## License

This security policy is part of the CRUDAdmin project and is subject to the same license terms.

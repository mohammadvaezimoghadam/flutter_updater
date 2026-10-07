#!/usr/bin/env python
"""
Entrypoint forwarding to Django manage.py runserver for backward compatibility.
"""
import os
import sys

if __name__ == '__main__':
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ota_hub.settings')
    from django.core.management import execute_from_command_line
    port = os.getenv("PORT", "8080")
    execute_from_command_line(['manage.py', 'runserver', f'0.0.0.0:{port}'])

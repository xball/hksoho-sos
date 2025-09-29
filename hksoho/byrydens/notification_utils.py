import frappe
from datetime import datetime
import pytz

@frappe.whitelist()
def convert_to_user_timezone(dt, user_email):
    try:
        # Default to system timezone or Hong Kong if user_email is invalid
        if not user_email or user_email == "Undefined":
            user_timezone = frappe.db.get_single_value('System Settings', 'time_zone') or 'Asia/Hong_Kong'
        else:
            # Get the user's timezone from their User profile
            user_timezone = frappe.db.get_value('User', user_email, 'time_zone')
            if not user_timezone:
                user_timezone = frappe.db.get_single_value('System Settings', 'time_zone') or 'Asia/Hong_Kong'
        
        # Convert UTC datetime to user's timezone
        if isinstance(dt, datetime):
            utc_dt = dt
        else:
            # Handle string datetime
            utc_dt = datetime.strptime(str(dt), '%Y-%m-%d %H:%M:%S.%f')
        
        user_tz = pytz.timezone(user_timezone)
        local_dt = utc_dt.replace(tzinfo=pytz.UTC).astimezone(user_tz)
        
        # Format the datetime (e.g., "2025-09-27 18:31:01 CET")
        return local_dt.strftime('%Y-%m-%d %H:%M:%S %Z')
    except Exception as e:
        # Log error and return original datetime as fallback
        frappe.log_error(f"Timezone conversion failed for user {user_email}: {str(e)}")
        return str(dt)
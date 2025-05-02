"""
Endpoints for managing families in the question-answer system.
"""

import logging
from fastapi import APIRouter, HTTPException, Request, Form, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import os
import uuid
from database import get_db_connection, is_admin_user, get_family_mqtt_config, update_family_mqtt_config, add_mqtt_device_to_family, remove_mqtt_device_from_family
from request_models import FamilyCreationRequest, FamilyMemberAddRequest, MQTTConfigRequest, MQTTDeviceInfo, MQTTMessageRequest
import psycopg2.extras
from mqtt_service import get_mqtt_service

# Create Router
router = APIRouter()

# Configure templates
current_dir = os.path.dirname(os.path.abspath(__file__))
templates_dir = os.path.join(current_dir, "templates")
templates = Jinja2Templates(directory=templates_dir)

# Setup Logging
logger = logging.getLogger(__name__)

@router.get("/families", response_class=HTMLResponse)
async def list_families(request: Request):
    """List all families the user belongs to (HTML view)"""
    return templates.TemplateResponse(
        "families.html", 
        {"request": request}
    )
    
@router.get("/families/check-admin/{user_id}")
async def check_admin(user_id: str):
    """Check if a user is an admin"""
    try:
        # Verify UUID
        try:
            import uuid
            user_uuid = uuid.UUID(user_id)
        except ValueError:
            raise HTTPException(
                status_code=400, 
                detail="Invalid user ID format. Must be a valid UUID."
            )
        
        # Check admin status
        from database import is_admin_user
        is_admin = is_admin_user(str(user_uuid))
        
        return {"is_admin": is_admin}
    
    except Exception as e:
        logger.error(f"Error checking admin status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/families/list")
async def get_families():
    """API endpoint to get list of all families"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Get all families with member count
        cursor.execute("""
            SELECT f.id, f.family_name, COUNT(u.id) AS member_count
            FROM families f
            LEFT JOIN users u ON f.id = u.family_id
            GROUP BY f.id, f.family_name
            ORDER BY f.family_name
        """)
        
        families = []
        for row in cursor.fetchall():
            families.append({
                "id": str(row["id"]),  # Convert UUID to string
                "family_name": row["family_name"],
                "member_count": row["member_count"]
            })
            
        return families
        
    except Exception as e:
        logger.error(f"Error getting families: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    
    finally:
        cursor.close()
        conn.close()

async def get_all_family_members():
    """Helper function to get members of all families"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Get all families
        cursor.execute("SELECT id, family_name FROM families ORDER BY family_name")
        families = cursor.fetchall()
        
        result = {
            "families": []
        }
        
        # For each family, get members
        for family in families:
            family_data = {
                "family_id": str(family["id"]),
                "family_name": family["family_name"],
                "members": []
            }
            
            cursor.execute("""
                SELECT id, username, phone_number, is_verified, created_at 
                FROM users
                WHERE family_id = %s
                ORDER BY created_at
            """, (family["id"],))
            
            members = cursor.fetchall()
            
            for member in members:
                family_data["members"].append({
                    "user_id": str(member["id"]),
                    "username": member["username"],
                    "phone_number": member["phone_number"],
                    "is_verified": member["is_verified"],
                    "joined_at": member["created_at"].isoformat() if member["created_at"] else None
                })
            
            result["families"].append(family_data)
            
        return result
        
    except Exception as e:
        logger.error(f"Error getting all family members: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    
    finally:
        cursor.close()
        conn.close()

@router.get("/families/{family_id}/members")
async def get_family_members(family_id: str):
    """Get all members of a specific family"""
    try:
        # Check if we need to get all families for this user
        if family_id.lower() == "all":
            return await get_all_family_members()
        
        # Try to parse as UUID - this handles proper validation
        try:
            import uuid
            family_uuid = uuid.UUID(family_id)
        except ValueError:
            raise HTTPException(
                status_code=400, 
                detail="Invalid family ID format. Must be a valid UUID."
            )
            
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # First verify the family exists
        cursor.execute("SELECT id, family_name FROM families WHERE id = %s", (str(family_uuid),))
        family = cursor.fetchone()
        
        if not family:
            raise HTTPException(status_code=404, detail="Family not found")
            
        # Get all members of this family
        cursor.execute("""
            SELECT id, username, phone_number, is_verified, created_at 
            FROM users
            WHERE family_id = %s
            ORDER BY created_at
        """, (family_id,))
        
        members = cursor.fetchall()
        
        # Format response
        result = {
            "family_id": family["id"],
            "family_name": family["family_name"],
            "members": []
        }
        
        for member in members:
            result["members"].append({
                "user_id": member["id"],
                "username": member["username"],
                "phone_number": member["phone_number"],
                "is_verified": member["is_verified"],
                "joined_at": member["created_at"].isoformat() if member["created_at"] else None
            })
            
        return result
        
    except Exception as e:
        logger.error(f"Error getting family members: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    
    finally:
        cursor.close()
        conn.close()

@router.post("/families")
async def create_family(request: FamilyCreationRequest):
    """Create a new family (admin only)"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Check if user is admin if provided
        if request.user_id:
            from database import is_admin_user
            if not is_admin_user(request.user_id):
                raise HTTPException(
                    status_code=403,
                    detail="Only administrators can create new families"
                )
        
        # Create new family
        family_id = str(uuid.uuid4())
        cursor.execute(
            "INSERT INTO families (id, family_name) VALUES (%s, %s) RETURNING id",
            (family_id, request.family_name)
        )
        
        new_family = cursor.fetchone()
        
        # Update the user's family_id if provided
        if request.user_id:
            cursor.execute(
                "UPDATE users SET family_id = %s WHERE id = %s",
                (family_id, request.user_id)
            )
        
        conn.commit()
        
        return {"family_id": new_family["id"], "family_name": request.family_name}
        
    except Exception as e:
        logger.error(f"Error creating family: {e}")
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    
    finally:
        cursor.close()
        conn.close()

@router.post("/families/{family_id}/members")
async def add_family_member(family_id: str, request: FamilyMemberAddRequest):
    """Add a new member to a family"""
    try:
        # Try to parse as UUID
        try:
            import uuid
            family_uuid = uuid.UUID(family_id)
        except ValueError:
            raise HTTPException(
                status_code=400, 
                detail="Invalid family ID format. Must be a valid UUID."
            )
            
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # First verify the family exists
        cursor.execute("SELECT id FROM families WHERE id = %s", (str(family_uuid),))
        family = cursor.fetchone()
        
        if not family:
            raise HTTPException(status_code=404, detail="Family not found")
            
        # Check if member exists
        cursor.execute("SELECT id, family_id FROM users WHERE phone_number = %s", (request.phone_number,))
        existing_user = cursor.fetchone()
        
        if not existing_user:
            raise HTTPException(status_code=404, detail="User not found")
            
        # Update user's family
        cursor.execute(
            "UPDATE users SET family_id = %s WHERE id = %s",
            (family_id, existing_user["id"])
        )
        
        conn.commit()
        
        return {"message": "Member added to family successfully"}
        
    except Exception as e:
        logger.error(f"Error adding family member: {e}")
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    
    finally:
        cursor.close()
        conn.close()
        
# MQTT-related endpoints

@router.get("/families/{family_id}/mqtt")
async def get_mqtt_config(family_id: str, user_id: str = None):
    """
    Get MQTT configuration for a family.
    
    Args:
        family_id: The family ID to get configuration for
        user_id: Optional user ID to check permissions
    """
    try:
        # Parse UUID to validate format
        try:
            family_uuid = uuid.UUID(family_id)
        except ValueError:
            raise HTTPException(
                status_code=400, 
                detail="Invalid family ID format. Must be a valid UUID."
            )
        
        # Optional admin check if user_id is provided
        if user_id:
            try:
                user_uuid = uuid.UUID(user_id)
                if not is_admin_user(str(user_uuid)):
                    raise HTTPException(
                        status_code=403,
                        detail="Only administrators can view MQTT configuration"
                    )
            except ValueError:
                raise HTTPException(
                    status_code=400, 
                    detail="Invalid user ID format. Must be a valid UUID."
                )
        
        # Get MQTT config
        config = get_family_mqtt_config(str(family_uuid))
        
        if not config:
            raise HTTPException(
                status_code=404,
                detail="Family not found or has no MQTT configuration"
            )
            
        # Mask the password for security
        if config.get("mqtt_password"):
            config["mqtt_password"] = "***********"
            
        return config
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting MQTT config: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/families/{family_id}/mqtt")
async def update_mqtt_config(family_id: str, config: MQTTConfigRequest, user_id: str = None):
    """
    Update MQTT configuration for a family.
    
    Args:
        family_id: The family ID to update
        config: MQTT configuration request
        user_id: Optional user ID to check permissions
    """
    try:
        # Parse UUID to validate format
        try:
            family_uuid = uuid.UUID(family_id)
        except ValueError:
            raise HTTPException(
                status_code=400, 
                detail="Invalid family ID format. Must be a valid UUID."
            )
        
        # Admin check if user_id is provided
        if user_id:
            try:
                user_uuid = uuid.UUID(user_id)
                if not is_admin_user(str(user_uuid)):
                    raise HTTPException(
                        status_code=403,
                        detail="Only administrators can update MQTT configuration"
                    )
            except ValueError:
                raise HTTPException(
                    status_code=400, 
                    detail="Invalid user ID format. Must be a valid UUID."
                )
        
        # Update MQTT config
        result = update_family_mqtt_config(str(family_uuid), config)
        
        if "error" in result:
            raise HTTPException(
                status_code=400,
                detail=result["error"]
            )
            
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating MQTT config: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/families/{family_id}/mqtt/devices")
async def add_mqtt_device(family_id: str, device: MQTTDeviceInfo, user_id: str = None):
    """
    Add a new allowed MQTT device to a family.
    
    Args:
        family_id: The family ID to update
        device: Device information
        user_id: Optional user ID to check permissions
    """
    try:
        # Parse UUID to validate format
        try:
            family_uuid = uuid.UUID(family_id)
        except ValueError:
            raise HTTPException(
                status_code=400, 
                detail="Invalid family ID format. Must be a valid UUID."
            )
        
        # Admin check if user_id is provided
        if user_id:
            try:
                user_uuid = uuid.UUID(user_id)
                if not is_admin_user(str(user_uuid)):
                    raise HTTPException(
                        status_code=403,
                        detail="Only administrators can add MQTT devices"
                    )
            except ValueError:
                raise HTTPException(
                    status_code=400, 
                    detail="Invalid user ID format. Must be a valid UUID."
                )
        
        # Add the device
        result = add_mqtt_device_to_family(
            str(family_uuid), 
            device.device_name,
            device.device_type
        )
        
        if "error" in result:
            raise HTTPException(
                status_code=400,
                detail=result["error"]
            )
            
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding MQTT device: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/families/{family_id}/mqtt/devices/{device_id}")
async def remove_mqtt_device(family_id: str, device_id: str, user_id: str = None):
    """
    Remove an allowed MQTT device from a family.
    
    Args:
        family_id: The family ID to update
        device_id: ID of the device to remove
        user_id: Optional user ID to check permissions
    """
    try:
        # Parse UUID to validate format
        try:
            family_uuid = uuid.UUID(family_id)
        except ValueError:
            raise HTTPException(
                status_code=400, 
                detail="Invalid family ID format. Must be a valid UUID."
            )
        
        # Admin check if user_id is provided
        if user_id:
            try:
                user_uuid = uuid.UUID(user_id)
                if not is_admin_user(str(user_uuid)):
                    raise HTTPException(
                        status_code=403,
                        detail="Only administrators can remove MQTT devices"
                    )
            except ValueError:
                raise HTTPException(
                    status_code=400, 
                    detail="Invalid user ID format. Must be a valid UUID."
                )
        
        # Remove the device
        result = remove_mqtt_device_from_family(str(family_uuid), device_id)
        
        if "error" in result:
            raise HTTPException(
                status_code=400,
                detail=result["error"]
            )
            
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing MQTT device: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/families/{family_id}/mqtt/connected-devices")
async def get_connected_mqtt_devices(family_id: str, user_id: str = None):
    """
    Get list of currently connected MQTT devices for a family.
    
    Args:
        family_id: The family ID to check
        user_id: Optional user ID to check permissions
    """
    try:
        # Parse UUID to validate format
        try:
            family_uuid = uuid.UUID(family_id)
        except ValueError:
            raise HTTPException(
                status_code=400, 
                detail="Invalid family ID format. Must be a valid UUID."
            )
        
        # Admin check if user_id is provided
        if user_id:
            try:
                user_uuid = uuid.UUID(user_id)
                if not is_admin_user(str(user_uuid)):
                    raise HTTPException(
                        status_code=403,
                        detail="Only administrators can view connected devices"
                    )
            except ValueError:
                raise HTTPException(
                    status_code=400, 
                    detail="Invalid user ID format. Must be a valid UUID."
                )
        
        # Get connected devices
        mqtt_service = get_mqtt_service()
        connected_devices = mqtt_service.get_connected_clients(str(family_uuid))
        
        return {
            "family_id": str(family_uuid),
            "connected_devices": connected_devices
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting connected MQTT devices: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/families/{family_id}/mqtt/send-message")
async def send_mqtt_message(family_id: str, message: MQTTMessageRequest, user_id: str = None):
    """
    Send a message to MQTT devices in a family.
    
    Args:
        family_id: The family ID to send to
        message: Message details
        user_id: Optional user ID to check permissions
    """
    try:
        # Parse UUID to validate format
        try:
            family_uuid = uuid.UUID(family_id)
        except ValueError:
            raise HTTPException(
                status_code=400, 
                detail="Invalid family ID format. Must be a valid UUID."
            )
        
        # Admin check if user_id is provided
        if user_id:
            try:
                user_uuid = uuid.UUID(user_id)
                if not is_admin_user(str(user_uuid)):
                    raise HTTPException(
                        status_code=403,
                        detail="Only administrators can send MQTT messages"
                    )
            except ValueError:
                raise HTTPException(
                    status_code=400, 
                    detail="Invalid user ID format. Must be a valid UUID."
                )
        
        # Get MQTT configuration to verify it's enabled
        config = get_family_mqtt_config(str(family_uuid))
        
        if not config:
            raise HTTPException(
                status_code=404,
                detail="Family not found"
            )
            
        if not config.get("mqtt_enabled", False):
            raise HTTPException(
                status_code=400,
                detail="MQTT is not enabled for this family"
            )
        
        # Send the message
        mqtt_service = get_mqtt_service()
        
        message_data = {
            "content": message.content,
            "type": message.message_type
        }
        
        if message.metadata:
            message_data.update(message.metadata)
        
        if message.device_id:
            # Send to specific device
            result = mqtt_service.send_message_to_device(
                str(family_uuid),
                message.device_id,
                message.message_type,
                message_data
            )
        else:
            # Send to all family devices
            topic = f"scribe/families/{family_uuid}/{message.message_type}"
            result = mqtt_service.publish(topic, message_data)
        
        if not result:
            raise HTTPException(
                status_code=500,
                detail="Failed to send MQTT message"
            )
            
        return {"success": True, "message": "Message sent successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending MQTT message: {e}")
        raise HTTPException(status_code=500, detail=str(e))
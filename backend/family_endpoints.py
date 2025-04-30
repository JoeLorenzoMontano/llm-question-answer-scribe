"""
Endpoints for managing families in the question-answer system.
"""

import logging
from fastapi import APIRouter, HTTPException, Request, Form, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import os
import uuid
from database import get_db_connection
from request_models import FamilyCreationRequest, FamilyMemberAddRequest
import psycopg2.extras

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
from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, status
from pydantic import BaseModel
from supabase import create_client, Client
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pymongo import MongoClient
from bson.objectid import ObjectId
import hashlib
import os
from datetime import datetime

# Supabase configuration (placeholders)
SUPABASE_URL = "https://cyhqxwjzmwflwgjglmop.supabase.co" # Replace with your Supabase project URL
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImN5aHF4d2p6bXdmbHdnamdsbW9wIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc1NTU0MDk5NiwiZXhwIjoyMDcxMTE2OTk2fQ.LQNIbADoLWCRHE6Rp8FjckIoB_52iXCfnOTPVnDIvto"  # Replace with your Supabase anon key
SUPABASE_BUCKET_NAME = "Project_new"  # Replace with your bucket name

# MongoDB setup (replace with your connection string)
MONGO_URL = "mongodb+srv://kaustubhshitole06:v3xp8diw2etvJ4SU@cluster0.2h4urer.mongodb.net/"

# Initialize clients
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
client = MongoClient(MONGO_URL)

# Select databases
db = client["role_based_app"]
users_collection = db["users"]
# Store uploaded file metadata in MongoDB
files_collection = db["files"]

app = FastAPI()

# Serve static files
 # app.mount("/static", StaticFiles(directory="static"), name="static")

 # Route to serve index.html at root (disabled for Vercel static hosting)
 # @app.get("/")
 # def serve_index():
 #     return FileResponse("index.html")


class FileUploadResponse(BaseModel):
    url: str
    message: str

# Registration request model
class RegisterRequest(BaseModel):
    username: str
    password: str
    role: str = "user"
    dob: str = ""
    phone: str = ""

@app.post("/upload", response_model=FileUploadResponse)
async def upload_file(file: UploadFile = File(...)):
    try:
        file_content = await file.read()
        file_extension = os.path.splitext(file.filename)[1]
        file_key = f"uploads/{file.filename}"
        print(f"Uploading to Supabase: bucket={SUPABASE_BUCKET_NAME}, key={file_key}, content_type={file.content_type}")
        # Upload to Supabase Storage
        response = supabase.storage.from_(SUPABASE_BUCKET_NAME).upload(
            file_key,
            file_content,
            {'content-type': file.content_type}
        )
        print(f"Supabase upload response: {response}")
        if hasattr(response, 'error') and response.error:
            print(f"Supabase error: {response.error}")
            raise HTTPException(status_code=500, detail=f"Supabase error: {response.error}")
        # Get public URL
        file_url = supabase.storage.from_(SUPABASE_BUCKET_NAME).get_public_url(file_key)
        print(f"Public URL: {file_url}")
        return FileUploadResponse(url=file_url, message="File uploaded successfully.")
    except Exception as e:
        print(f"Exception during upload: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to upload file: {str(e)}")

security = HTTPBasic()

# Helper functions

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password: str, hashed: str) -> bool:
    return hash_password(password) == hashed

def get_user(username: str):
    return users_collection.find_one({"username": username})

def create_user(username: str, password: str, role: str, dob: str = "", phone: str = ""):
    if get_user(username):
        return None
    user = {
        "username": username,
        "password": hash_password(password),  # Store only hash
        "role": role,
        "dob": dob,
        "phone": phone
    }
    users_collection.insert_one(user)
    return user

def get_current_user(credentials: HTTPBasicCredentials = Depends(security)):
    user = get_user(credentials.username)
    if not user or not verify_password(credentials.password, user["password"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    return user

def get_admin_user(user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


# Registration endpoint (accepts JSON)

@app.post("/register")
def register(request: RegisterRequest):
    import traceback
    print(f"Registration attempt: username={request.username}, role={request.role}, dob={request.dob}, phone={request.phone}")
    try:
        # Check MongoDB connection
        try:
            client.admin.command('ping')
        except Exception as db_exc:
            print(f"MongoDB connection error: {db_exc}")
            return {"error": "Database connection failed. Check credentials and network."}

        if request.role not in ["user", "admin"]:
            print("Invalid role provided.")
            return {"error": "Role must be 'user' or 'admin'"}
        if request.role == "admin":
            admin_count = users_collection.count_documents({"role": "admin"})
            print(f"Current admin count: {admin_count}")
            if admin_count >= 4:
                print("Admin limit reached.")
                return {"error": "Maximum number of admin users (4) reached"}
        user = create_user(request.username, request.password, request.role, request.dob, request.phone)
        if not user:
            print("Username already exists.")
            return {"error": "Username already exists"}
        print("User registered successfully.")
        return {"message": "User registered successfully"}
    except Exception as e:
        print(f"Exception in /register: {e}\n{traceback.format_exc()}")
        return {"error": f"Registration failed: {str(e)}"}

# Login endpoint (for demonstration, returns success message)
@app.post("/login")
def login(credentials: HTTPBasicCredentials = Depends(security)):
    user = get_current_user(credentials)
    return {"message": f"Welcome {user['username']}!", "role": user["role"]}

# User: view own profile (include dob, phone)
@app.get("/me")
def get_me(user=Depends(get_current_user)):
    return {"username": user["username"], "role": user["role"], "dob": user.get("dob", ""), "phone": user.get("phone", "")}

# User: update own password
@app.put("/me/password")
def update_password(new_password: str, user=Depends(get_current_user)):
    users_collection.update_one({"_id": user["_id"]}, {"$set": {"password": hash_password(new_password)}})
    return {"message": "Password updated successfully"}

# Admin: view all users (include dob, phone)
@app.get("/admin/users")
def get_all_users(admin=Depends(get_admin_user)):
    users = list(users_collection.find({}, {"_id": 0, "password": 0}))
    return {"users": users}

# Update upload_file endpoint to save metadata
@app.post("/upload_file")
async def upload_file(file: UploadFile = File(...), user=Depends(get_current_user)):
    try:
        file_content = await file.read()
        file_extension = os.path.splitext(file.filename)[1]
        file_key = f"uploads/{user['username']}/{file.filename}"
        print(f"Uploading to Supabase: bucket={SUPABASE_BUCKET_NAME}, key={file_key}, content_type={file.content_type}")
        response = supabase.storage.from_(SUPABASE_BUCKET_NAME).upload(
            file_key,
            file_content,
            {'content-type': file.content_type}
        )
        print(f"Supabase upload response: {response}")
        if hasattr(response, 'error') and response.error:
            print(f"Supabase error: {response.error}")
            raise HTTPException(status_code=500, detail=f"Supabase error: {response.error}")
        file_url = supabase.storage.from_(SUPABASE_BUCKET_NAME).get_public_url(file_key)
        print(f"Public URL: {file_url}")
        # Save file metadata
        files_collection.insert_one({
            "username": user["username"],
            "filename": file.filename,
            "file_url": file_url,
            "content_type": file.content_type,
            "uploaded_at": datetime.utcnow()
        })
        return {"url": file_url, "message": "File uploaded successfully."}
    except Exception as e:
        print(f"Exception during upload: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to upload file: {str(e)}")

# Admin: view all users and their files
@app.get("/admin/users/details")
def get_all_users_details(admin=Depends(get_admin_user)):
    users = list(users_collection.find({}, {"_id": 0, "password": 0}))
    for user in users:
        user_files = list(files_collection.find({"username": user["username"]}, {"_id": 0}))
        user["files"] = user_files
    return {"users": users}







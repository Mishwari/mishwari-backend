#!/bin/bash

# --- CONFIGURATION ---
# Your Google Web API Key (From GCP Credentials page)
API_KEY="AIzaSyD..." 
# The Test Number you added in console
PHONE="+967770000000"
# The Test Code you added in console
CODE="123456"
# Your Django Local Server
DJANGO_URL="http://127.0.0.1:8000/api/auth/verify/"

echo "---------------------------------------------------"
echo "1. Simulating 'Send SMS' (Getting Session Info)..."
echo "---------------------------------------------------"

# We call Google to start the flow. 
# Note: For test numbers, this doesn't send SMS, but we need the sessionInfo.
SESSION_RESPONSE=$(curl -s -X POST "https://identitytoolkit.googleapis.com/v1/accounts:sendVerificationCode?key=$API_KEY" \
-H "Content-Type: application/json" \
-d "{ \"phoneNumber\": \"$PHONE\", \"recaptchaToken\": \"dummy_token_for_test_numbers\" }")

# Extract sessionInfo using grep/sed (simple parsing)
SESSION_INFO=$(echo $SESSION_RESPONSE | grep -o '"sessionInfo": *"[^"]*"' | cut -d'"' -f4)

if [ -z "$SESSION_INFO" ]; then
    echo "❌ Error: Could not get Session Info. Check API Key or Test Number."
    echo "Response: $SESSION_RESPONSE"
    exit 1
fi

echo "✅ Session Info Acquired."

echo "---------------------------------------------------"
echo "2. Simulating 'User Entering Code' (Logging In)..."
echo "---------------------------------------------------"

# We exchange the Code + SessionInfo for an ID Token
LOGIN_RESPONSE=$(curl -s -X POST "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPhoneNumber?key=$API_KEY" \
-H "Content-Type: application/json" \
-d "{ \"sessionInfo\": \"$SESSION_INFO\", \"code\": \"$CODE\" }")

# Extract ID Token
ID_TOKEN=$(echo $LOGIN_RESPONSE | grep -o '"idToken": *"[^"]*"' | cut -d'"' -f4)

if [ -z "$ID_TOKEN" ]; then
    echo "❌ Error: Login failed."
    echo "Response: $LOGIN_RESPONSE"
    exit 1
fi

echo "✅ Login Successful. Token acquired."
# Optional: Print first few chars of token
echo "Token: ${ID_TOKEN:0:20}..."

echo "---------------------------------------------------"
echo "3. Sending Token to Django Backend..."
echo "---------------------------------------------------"

# We send the token to Django to verify it's real
DJANGO_RESPONSE=$(curl -s -X POST "$DJANGO_URL" \
-H "Content-Type: application/json" \
-d "{ \"id_token\": \"$ID_TOKEN\" }")

echo "Django Response: $DJANGO_RESPONSE"
echo "---------------------------------------------------"
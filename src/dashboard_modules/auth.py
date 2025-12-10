import requests

def get_login_url(api_key, redirect_uri):
    return f"https://api.upstox.com/v2/login/authorization/dialog?response_type=code&client_id={api_key}&redirect_uri={redirect_uri}"

def exchange_code_for_token(auth_code, api_key, api_secret, redirect_uri):
    url = 'https://api.upstox.com/v2/login/authorization/token'
    headers = {'accept': 'application/json', 'Content-Type': 'application/x-www-form-urlencoded'}
    data = {
        'code': auth_code,
        'client_id': api_key,
        'client_secret': api_secret,
        'redirect_uri': redirect_uri,
        'grant_type': 'authorization_code',
    }
    try:
        resp = requests.post(url, headers=headers, data=data)
        if resp.status_code == 200:
            token = resp.json()['access_token']
            # 🚨 RETURN THE TOKEN SO DASHBOARD CAN SAVE IT
            return True, token 
        else:
            return False, f"Upstox Error: {resp.text}"
    except Exception as e:
        return False, str(e)
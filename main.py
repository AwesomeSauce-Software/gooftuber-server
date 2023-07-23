import os
import base64
import random
import threading
import time
import asyncio
import discord
from quart import Quart, request, websocket

token = "put token here :) definitely didnt leak it before here :)"

app = Quart(__name__)
client = discord.Client(intents=discord.Intents.all())
avatar_dir = 'avatars/'
verifications = {}
verified_sessions = {}

# used to allow other sessions to access the data like avatars, actions, etc.
sessions_allow_sessions = {
    # 'session_id': {
    #     'allowed_sessions': ['session_id', 'session_id']
    # }
}

session_ask_ids = {
    # 'inviteid': {
    #     'session_id': 'session_id'
    #     'allow_session_id': 'session_id'
    # }
}

current_data = {
    # 'session_id': {
    #     'voice_activity': 1.2,
    #     'action': 'action_from_expression_name'
    # }
}


@client.event
async def on_ready():
    print(f'We have logged in as {client.user}')


@app.route('/upload-avatar/<sessionid>', methods=['POST'])
async def upload_image(sessionid):
    """
    Uploads an avatar to the server. The avatar is stored in the avatars/ directory.
    :param sessionid: The session ID of the user uploading the avatar. This is used to verify the user's identity.
    """
    if sessionid not in verified_sessions:
        return {'message': 'Invalid session ID!'}, 401
    avatar_files = await request.files
    if 'avatar' not in avatar_files:
        return ({'message': 'No avatar file provided!'}), 400  # Return a response with a 400 Bad Request status
    avatar_files = avatar_files.getlist('avatar')  # 'avatar' should match the name used in the request
    results = []
    if not os.path.isdir("avatars/" + sessionid):
        os.mkdir("avatars/" + sessionid)
    else:
        for file in os.listdir("avatars/" + sessionid):
            os.remove("avatars/" + sessionid + "/" + file)
        os.rmdir("avatars/" + sessionid)
        os.mkdir("avatars/" + sessionid)
    for file in avatar_files:
        filename = file.filename
        if filename.endswith('.png'):
            base64_string = base64.b64encode(file.read()).decode('utf-8')
            with open(avatar_dir + sessionid + '/' + filename, 'wb') as f:
                f.write(base64.b64decode(base64_string))
            results.append({'filename': filename, 'base64': base64_string})

    return {'avatars': results, 'message': 'Avatar files uploaded successfully!'}


def does_user_exist(userid):
    """
        Checks if a user exists in the server.
        :param userid: The user ID of the user to check.
        """
    for session in verified_sessions:
        if verified_sessions[session] == userid:
            return True
    return False


def get_session_id(userid) -> str:
    """
    Gets the session ID of a user.
    :param userid:
    :return:
    """
    for session in verified_sessions:
        if verified_sessions[session] == userid:
            return session
    return None


@app.route('/request-session/<sourcesession>/<userid>', methods=['GET'])
async def request_session(sourcesession, userid):
    """
    Requests access to a session. The user will be sent a message with a link to allow access to the session.
    :param sourcesession: The session ID of the user requesting access.
    :param userid: The user ID of the user to request access to.
    :return:
    """
    if sourcesession not in verified_sessions:
        return {'message': 'Invalid session ID!'}
    if not does_user_exist(userid):
        return {'message': 'Invalid user ID!'}
    session_invite_id = ""
    for i in range(10):
        session_invite_id += str(random.randint(0, 9))
    session_ask_ids[session_invite_id] = {
        'session_id': sourcesession,
        'allow_session_id': get_session_id(userid)
    }
    await send_message(userid, f'User <@{verified_sessions[sourcesession]}> is requesting access to your session. Open '
                               f'this link to allow access: https://api.ptgms.space/allow-session/{session_invite_id}')
    return {'message': 'Session request sent!'}


@app.route('/allow-session/<invite_id>', methods=['GET'])
async def allow_session(invite_id):
    """
    User allows another user to access their session.
    :param invite_id: The invite ID of the session.
    :return:
    """
    if invite_id not in session_ask_ids:
        return {'message': 'Invalid invite ID!'}, 401
    sessionid = session_ask_ids[invite_id]['session_id']
    allow_sessionid = session_ask_ids[invite_id]['allow_session_id']
    if sessionid not in verified_sessions:
        return {'message': 'Invalid session ID!'}
    if allow_sessionid not in verified_sessions:
        return {'message': 'Invalid session ID!'}
    if sessionid not in sessions_allow_sessions:
        sessions_allow_sessions[sessionid] = {
            'allowed_sessions': []
        }
    sessions_allow_sessions[sessionid]['allowed_sessions'].append(allow_sessionid)
    return {'message': 'Session allowed!'}


def load_verified_sessions():
    global verified_sessions
    if os.path.isfile('verified_sessions.txt'):
        with open('verified_sessions.txt', 'r') as f:
            verified_sessions = eval(f.read())
    else:
        verified_sessions = {}

    global sessions_allow_sessions
    if os.path.isfile('sessions_allow_sessions.txt'):
        with open('sessions_allow_sessions.txt', 'r') as f:
            sessions_allow_sessions = eval(f.read())
    else:
        sessions_allow_sessions = {}


def save_verified_sessions():
    while True:
        time.sleep(60)
        with open('verified_sessions.txt', 'w') as f:
            f.write(str(verified_sessions))

        with open('sessions_allow_sessions.txt', 'w') as f:
            f.write(str(sessions_allow_sessions))


def add_to_verified_sessions(user_id, session_id):
    # check if user is already verified, if so, remove the old session id
    if user_id in verified_sessions.values():
        for session in verified_sessions:
            if verified_sessions[session] == user_id:
                del verified_sessions[session]
                break
    verified_sessions[session_id] = user_id


async def send_message(user_id, message):
    user = await client.fetch_user(int(user_id))
    try:
        await user.send(message)
        return {'message': 'Message sent!'}
    except discord.Forbidden:
        return {'message': 'Unable to send message. User may have DMs disabled.'}, 400


@app.route('/verify/<userid>', methods=['GET'])
async def verify(userid):
    """
    Generates a verification code and sends it to the user.
    :param userid: The user ID of the user to send the verification code to.
    :return:
    """
    verification_code = "".join(str(random.randint(0, 9)) for _ in range(6))
    verifications[verification_code] = {
        'user_id': userid,
        'expires': time.time() + 300
    }
    await send_message(userid, f'Please verify your identity by entering this code in the software: '
                               f'{verification_code}\n\n'
                               'The code will expire in 5 minutes. If you did not request this verification code, '
                               'please ignore this message.')
    return {'message': 'Verification code generation initiated!'}


@app.route('/verify/<userid>/<code>', methods=['GET'])
async def verify_code(userid, code):
    """
    Verifies a user's identity.
    :param userid: The user ID of the user to verify.
    :param code: The verification code to verify.
    :return:
    """
    session_id = ""
    for i in range(10):
        session_id += str(random.randint(0, 9))
    if code in verifications:
        if verifications[code]['user_id'] == userid:
            if verifications[code]['expires'] > time.time():
                await send_message(userid, 'Verification successful! Have fun!')
                add_to_verified_sessions(userid, session_id)
                return {'message': 'Verification successful!', 'session_id': session_id}
            else:
                await send_message(userid, 'Verification expired! Please try again.')
                return {'message': 'Verification code expired!'}, 400
        else:
            await send_message(userid, 'Verification code incorrect! Please try again.')
            return {'message': 'Verification code incorrect!'}, 401
    else:
        await send_message(userid, 'Verification code incorrect! Please try again.')
        return {'message': 'Verification code incorrect!'}, 401


@app.route('/get-avatars/<sessionid>/<userid>', methods=['GET'])
async def get_avatars(sessionid, userid):
    """
    Gets all avatars of a user. Verifies that the session is allowed to access the avatars.
    :param sessionid: The sessionid initiating the request.
    :param userid: The user ID of the user to get the avatars of.
    :return:
    """
    #     check if session and user id are valid
    if sessionid not in verified_sessions:
        return {'message': 'Invalid session ID!'}
    if not does_user_exist(userid):
        return {'message': 'Invalid user ID!'}
    #    check if session is allowed to access avatar of user
    print(sessions_allow_sessions[sessionid]['allowed_sessions'])
    if sessions_allow_sessions[sessionid]['allowed_sessions'] is not None:
        if str(get_session_id(userid)) not in sessions_allow_sessions[sessionid]['allowed_sessions']:
            return {'message': 'Session not allowed to access avatar!'}
    else:
        return {'message': 'Session not allowed to access avatar!'}
    if not os.path.isdir("avatars/" + str(get_session_id(userid))):
        return {'message': 'No avatars found!'}
    avatars = []
    for file in os.listdir("avatars/" + str(get_session_id(userid))):
        with open("avatars/" + str(get_session_id(userid)) + "/" + file, 'rb') as f:
            avatars.append({
                'filename': file,
                'base64': base64.b64encode(f.read()).decode('utf-8')
            })
    return {'avatars': avatars}


@app.websocket('/receive-data/<sessionid>')
async def receive_data(sessionid):
    """
    Receives data from the clients connected to the server. Gives all data the session is allowed to access. You should
    use /receive-data/<sessionid>/<userid> instead for fewer data being sent.
    :param sessionid:
    :return:
    """
    #     get all current_data for what the session is allowed to access
    print("Connected to send data:", sessionid)
    prev = {}
    while True:
        response = {}
        for session in sessions_allow_sessions[sessionid]['allowed_sessions']:
            if session in current_data:
                userid = verified_sessions[session]
                response[userid] = current_data[session]
        if len(response) == 0:
            await websocket.send("No data available!")
            return
        if response != prev:
            await websocket.send(str(response))
            prev = response
        await asyncio.sleep(0.01)


@app.websocket('/receive-data/<sessionid>/<userid>')
async def receive_data_user(sessionid, userid):
    """
    Receives data from the clients connected to the server.
    :param sessionid:
    :param userid: UserID to get data of
    :return:
    """
    #     get all current_data for what the session is allowed to access
    print("Connected to send data:", sessionid)
    prev = {}
    while True:
        response = {}
        allowed_sessions = sessions_allow_sessions[sessionid]['allowed_sessions']
        if str(get_session_id(userid)) in allowed_sessions:
            if str(get_session_id(userid)) in current_data:
                response[userid] = current_data[str(get_session_id(userid))]
            else:
                return {'message': 'Data is not being sent!'}
        else:
            return {'message': 'Session not allowed to access data!'}
        if len(response) == 0:
            await websocket.send("No data available!")
            return
        if response != prev:
            await websocket.send(str(response))
            prev = response
        await asyncio.sleep(0.01)


@app.websocket('/send-data/<sessionid>')
async def send_data(sessionid):
    """
    Sends voice meter and current emotion to the server and stores it.
    :param sessionid:
    :return:
    """
    print("Connected to receive data:", sessionid)

    while True:
        data = await websocket.receive()
        print("Received data:", data)
        current_data[sessionid] = data
        await websocket.send("OK")


@app.before_serving
async def before_serving():
    if not os.path.isdir("avatars"):
        os.mkdir("avatars")
    load_verified_sessions()
    threading.Thread(target=save_verified_sessions).start()
    loop = asyncio.get_event_loop()
    await client.login(token)
    loop.create_task(client.connect())


if __name__ == '__main__':
    Quart.run(app, host='0.0.0.0', port=5000, debug=False)

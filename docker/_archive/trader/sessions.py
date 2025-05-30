import json

import requests


class TastyworksSession:
    def __init__(self, username, password, remember_me=False):
        self.username = username
        self.password = password
        self.remember_me = remember_me

    def __enter__(self):
        self.session = self.create_session(self.username, self.password, remember_me=False)  # Define your function here.
        return self.session

    def __exit__(self, exc_type, exc_val, exc_tb):
        # If an exception has occurred, exc_type will be the type of the exception.
        # Alternatively, you can also use `exc_val`, which is the instance of the exception
        if exc_type is not None:
            print("Exception has been caught", exc_type, exc_val, exc_tb)
            # Handle exception here.
        self.destroy_session(self.session["session-token"])  # Define your function here.

    @staticmethod
    def create_session(username, password, remember_me):
        """
        Creates a session with the Tastyworks API using the provided username and password.

        :param username: A string representing the username to authenticate with.
        :param password: A string representing the password to authenticate with.
        :param remember_me: A boolean indicating whether to remember the session (default is True).
        :return: The session data if the session is successfully created.
        :raises: Exception if the session creation fails.

        """
        url = "https://api.tastyworks.com/sessions"
        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }
        data = {
            "login": username,
            "password": password,
            "remember-me": remember_me
        }

        response = requests.post(url, data=json.dumps(data), headers=headers)

        if response.status_code in (200, 201):
            session_data = response.json()
            return session_data["data"]
        else:
            raise Exception(f"Failed to create session. Status code: {response.status_code}")

    @staticmethod
    def destroy_session(session_token):
        url = "https://api.tastyworks.com/sessions"
        headers = {
            'Authorization': session_token,
            'Content-Type': 'application/json'
        }

        response = requests.delete(url, headers=headers)

        if response.status_code == 204:
            print("Session destroyed successfully.")
        else:
            raise Exception(f"Failed to destroy session. Status code: {response.status_code}")

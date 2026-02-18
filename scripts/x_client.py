import os
from xdk import Client
from xdk.oauth1_auth import OAuth1



def main():
    api_key = os.getenv("X_CONSUMER_KEY")
    api_secret = os.getenv("X_SECRET_KEY")
    access_token = os.getenv("X_ACCESS_TOKEN")
    access_token_secret = os.getenv("X_ACCESS_TOKEN_SECRET")

    oauth1 = OAuth1(
        api_key,
        api_secret,
        callback="http://localhost:3000/callback",
        access_token=access_token,
        access_token_secret=access_token_secret,
    )

    client = Client(
        auth=oauth1
    )

    response = client.users.get_me()
    me = response.data
    print(me)

    payload = {"text": "hello, ai world"}
    post = client.posts.create(body=payload)

    # ex) data=CreateResponseData(id='2022546038977106418', text='hello, ai world') errors=None
    print(post)


if __name__ == "__main__":
    main()

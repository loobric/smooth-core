# Quick Start

Smooth Core is brand new and not yet ready for production use.  If you're looking for a production ready solution, you will have to wait a bit.  If you're a curious developer or risk tolerant user, you can try it out by running it yourself.

1. Clone the repository

```
git clone https://github.com/loobric/smooth-core.git
```

2. Activate the virtual environment and install dependencies

```
cd smooth-core
uv venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
uv pip install -e ".[dev]"
```

3. Run the server

```
uvicorn smooth.main:app --reload
```

4. Create the admin user.

The first user created will automatically be the admin user.
You can create a user account with the command line utility.

```
  loobric.py --base-url http://127.0.0.1:8000 register admin@example.com
```

5. Login as the admin user

```
  loobric.py --base-url http://127.0.0.1:8000 login admin@example.com
```

Create an access token

```
  loobric.py create-key "Backup Script" \
    --scopes "read" --tags "backup production" --expires-at "2025-12-31T23:59:59Z"
```

6. Record the token

The previous command will echo the token back to the console in clear text. Only the token hash is stored in the database so the actual token can not be recovered.  Write it down or store it securely.

7. Use the token in one of the cliens like [smooth-freecad](https://github.com/loobric/smooth-freecad)
# Copyright (c) 2018 Yubico AB
# All rights reserved.
#
#   Redistribution and use in source and binary forms, with or
#   without modification, are permitted provided that the following
#   conditions are met:
#
#    1. Redistributions of source code must retain the above copyright
#       notice, this list of conditions and the following disclaimer.
#    2. Redistributions in binary form must reproduce the above
#       copyright notice, this list of conditions and the following
#       disclaimer in the documentation and/or other materials provided
#       with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
# FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
# COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
# ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

"""
Connects to the first FIDO device found (starts from USB, then looks into NFC),
creates a new credential for it, and authenticates the credential.
This works with both FIDO 2.0 devices as well as with U2F devices.
On Windows, the native WebAuthn API will be used.
"""
from __future__ import print_function, absolute_import, unicode_literals

from fido2.hid import CtapHidDevice
from fido2.ctap2 import ClientPin, LargeBlobs
from fido2.client import Fido2Client
from fido2.server import Fido2Server
from getpass import getpass
import sys


pin = None
uv = "discouraged"

# Locate a device
dev = next(CtapHidDevice.list_devices(), None)
if dev is not None:
    print("Use USB HID channel.")
else:
    try:
        from fido2.pcsc import CtapPcscDevice

        dev = next(CtapPcscDevice.list_devices(), None)
        print("Use NFC channel.")
    except Exception as e:
        print("NFC channel search error:", e)

if not dev:
    print("No FIDO device found")
    sys.exit(1)

# Set up a FIDO 2 client using the origin https://example.com
client = Fido2Client(dev, "https://example.com")

if not client.info.options.get("largeBlobs"):
    print("Authenticator does not support large blobs!")
    sys.exit(1)

if "largeBlobKey" not in client.info.extensions:
    print("Authenticator does not support the largeBlobKey extension!")
    sys.exit(1)


# Prefer UV if supported
if client.info.options.get("uv"):
    uv = "preferred"
    print("Authenticator supports User Verification")
elif client.info.options.get("clientPin"):
    # Prompt for PIN if needed
    pin = getpass("Please enter PIN: ")
else:
    print("PIN not set, won't use")


server = Fido2Server({"id": "example.com", "name": "Example RP"}, attestation="direct")

user = {"id": b"user_id", "name": "A. User"}

# Prepare parameters for makeCredential
create_options, state = server.register_begin(
    user,
    resident_key=True,
    user_verification=uv,
    authenticator_attachment="cross-platform",
)

# Enable largeBlobKey
options = create_options["publicKey"]
options.extensions = {"largeBlobKey": True}

# Create a credential
print("\nTouch your authenticator device now...\n")

attestation_object, client_data = client.make_credential(options, pin=pin)
key = attestation_object.large_blob_key

# Complete registration
auth_data = server.register_complete(state, client_data, attestation_object)
credentials = [auth_data.credential_data]

print("New credential created!")
print("Large Blob Key:", key)

client_pin = ClientPin(client.ctap2)
token = client_pin.get_pin_token(pin, ClientPin.PERMISSION.LARGE_BLOB_WRITE)
large_blobs = LargeBlobs(client.ctap2, client_pin.protocol, token)

# Write a large blob
print("Writing a large blob...")
large_blobs.put_blob(key, b"Here is some data to store!")

# Prepare parameters for getAssertion
request_options, state = server.authenticate_begin(user_verification=uv)

# Enable largeBlobKey
options = request_options["publicKey"]
options.extensions = {"largeBlobKey": True}

# Authenticate the credential
print("\nTouch your authenticator device now...\n")

assertions, client_data = client.get_assertion(options, pin=pin)
assertion = assertions[0]  # Only one cred in allowCredentials, only one response.

# This should match the key from MakeCredential.
key = assertion.large_blob_key

# Get a fresh PIN token
token = client_pin.get_pin_token(pin, ClientPin.PERMISSION.LARGE_BLOB_WRITE)
large_blobs = LargeBlobs(client.ctap2, client_pin.protocol, token)

blob = large_blobs.get_blob(key)
print("Read blob", blob)

# Clean up
large_blobs.delete_blob(key)

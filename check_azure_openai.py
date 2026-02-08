#!/usr/bin/env python3
"""
Simple test script to check if Azure OpenAI is responding.
"""
import time

from openai import AzureOpenAI, AuthenticationError, BadRequestError, PermissionDeniedError

# Azure OpenAI Configuration
API_BASE = "https://aiml04openai.openai.azure.com"
API_KEY = "7d2b69007f844d729899b745a5c3eada"
API_VERSION = "2025-01-01-preview"
MODEL_NAME = "insta-gpt-4o"

print("=" * 60)
print("Testing Azure OpenAI Connection")
print("=" * 60)
print(f"Endpoint: {API_BASE}")
print(f"Model: {MODEL_NAME}")
print(f"API Version: {API_VERSION}")
print("-" * 60)

try:
    print("\n1. Initializing Azure OpenAI client...")

    client = AzureOpenAI(
        api_key=API_KEY,
        api_version=API_VERSION,
        azure_endpoint=API_BASE
    )
    print("   ✓ Client initialized successfully")

    print("\n2. Sending test request to GPT-4o...")
    success: bool = False
    MAX_ATTEMPT_COUNTER = 5
    attempt_counter = 1
    response = None
    while not success and attempt_counter <= MAX_ATTEMPT_COUNTER:
        try:
            print(f'Attempt - {attempt_counter}')
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": "Say hello and confirm you are responding."},
                ],
                temperature=0.7,
                max_tokens=100,
            )
            success = True
        except AuthenticationError as e:
            msg = 'LLM Authentication Error'
            print(msg)
            raise e
        except BadRequestError as e:
            msg = 'LLM Bad Request Error'
            print(msg)
            raise e
        except PermissionDeniedError as e:
            msg = 'LLM Permission Denied Error'
            print(msg)
            raise e

        except Exception as e:
            print(f"\n✗ Error occurred: {type(e).__name__}")
            attempt_counter += 1
            time.sleep(1)
            if not success and attempt_counter > MAX_ATTEMPT_COUNTER:
                print(f'LLM Codel - Chat Completion Not Working')
                print(f'\n✗ Failed After Attempts - {attempt_counter}:')
                print(f"\n✗ Error occurred: {type(e).__name__}")
                print(f"   Message: {e}")
                print("\n" + "=" * 60)
                import traceback

                print("\nFull traceback:")
                print(traceback.format_exc())
                print("=" * 60)
                exit(3)

    if response:
        print(f"   ✓ Request successful! In Attempts - {attempt_counter}")

        print("\n3. Response received:")
        print("-" * 60)
        output = response.choices[0].message.content
        print(output)
        print("-" * 60)

        print("\n✓ Azure OpenAI is working correctly!")
        print("=" * 60)

except Exception as e:
    print(f"\n✗ Error occurred: {type(e).__name__}")
    print(f"   Message: {e}")
    print("\n" + "=" * 60)
    import traceback

    print("\nFull traceback:")
    print(traceback.format_exc())
    print("=" * 60)

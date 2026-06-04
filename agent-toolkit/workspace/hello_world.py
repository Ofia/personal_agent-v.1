#!/usr/bin/env python3

def greet_user(name):
    """Function to greet a user by name"""
    return f"Hello, {name}! Nice to meet you!"

def main():
    """Main function"""
    print("Hello, World!")
    
    # Example usage of greet_user function
    user_name = "Alice"
    greeting = greet_user(user_name)
    print(greeting)

if __name__ == "__main__":
    main()
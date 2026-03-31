"""Main entry point for demo-package CLI."""


def main():
    """Call the C hello_world function and print the result."""
    import demo

    result = demo.world()
    print(result)


if __name__ == "__main__":
    main()

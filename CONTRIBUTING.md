# Contributing to Unraid Connect Integration

Thank you for your interest in contributing to the Unraid Connect integration for Home Assistant! This document provides guidelines and instructions for contributing.

## Code of Conduct

Please be respectful and considerate of others when contributing to this project. We aim to foster an inclusive and welcoming community.

## How Can I Contribute?

### Reporting Bugs

If you find a bug in the integration, please create an issue on GitHub with the following information:
- A clear, descriptive title
- Steps to reproduce the issue
- Expected behavior vs. actual behavior
- Home Assistant and Unraid versions
- Any relevant logs or error messages

### Suggesting Enhancements

We welcome suggestions for improvements or new features:
- Use a clear, descriptive title
- Provide a detailed description of the enhancement
- Explain why this enhancement would be useful
- Include examples of how it would be used

### Pull Requests

We actively welcome pull requests:

1. Fork the repository
2. Create a new branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests to ensure they pass: `pytest`
5. Format your code with pre-commit hooks: `pre-commit run --all-files`
6. Commit your changes (`git commit -m 'Add some amazing feature'`)
7. Push to your branch (`git push origin feature/amazing-feature`)
8. Open a Pull Request

## Development Setup

1. Clone the repository
2. Install development dependencies:
   ```bash
   pip install -r requirements-dev.txt
   ```
3. Install pre-commit hooks:
   ```bash
   pre-commit install
   ```

## Testing

All new code should include appropriate tests. Run the test suite with:

```bash
pytest
```

For coverage information:

```bash
pytest --cov=custom_components.unraid_connect
```

## Code Style

This project follows the Home Assistant code style:
- Type hints for all function parameters and return values
- Docstrings for all public methods and classes
- Pre-commit hooks for consistent formatting
- PEP 8 compliance

## Documentation

- Update README.md with details of changes to functionality
- Keep code comments up-to-date
- Add examples for new features

## License

By contributing to this project, you agree that your contributions will be licensed under the project's [Apache License](LICENSE).
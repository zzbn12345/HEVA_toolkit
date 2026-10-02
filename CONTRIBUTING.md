# Contributing to HEVA Toolkit

Thank you for helping improve HEVA. Contributions can be feedback, documentation,
test cases, or code. You do not need to be a programmer to contribute usefully.

## Before you start

- Do not add confidential, copyrighted, or personally sensitive source documents to
  this repository.
- Describe the problem in plain language. A screenshot and the steps that led to the
  problem are often more useful than technical terminology.
- Keep one contribution focused on one issue. For example: “the Approve button does
  not show that it was selected.”

## If you found a problem

Create a GitHub issue, or send the project team the following information:

1. What you were trying to do.
2. What you expected to happen.
3. What happened instead.
4. The document type and a safe example, if one can be shared.
5. A screenshot, error message, or the steps needed to repeat the problem.

Please remove names, unpublished research, and other sensitive details from examples
before sharing them.

## If you want to propose a change

Use a pull request. A pull request is a request to review a proposed change before it
becomes part of the project.

1. Make a copy of the repository in your own GitHub account (a *fork*), or create a
   new branch if you already have write access.
2. Make the smallest change that solves the issue.
3. Explain the change in ordinary language in the pull request description.
4. Say how someone can check it manually. For interface changes, add screenshots when
   practical.
5. Request review. Do not merge your own change without agreement from a project owner.

Pull requests aimed at `main` or `develop` automatically run the project test suite.
A green check means the automated checks passed; it does not replace human review.
If the check is red, ask for help or include the error message in the pull request.

## Commit messages and contents

A *commit* is a small saved change with a message that explains why it exists. It is
the basic unit that reviewers read, test, and—if necessary—undo. Make commits small
enough that each one has one clear purpose.

Each commit should contain:

- one related change, such as one bug fix, one documentation update, or one test
  improvement;
- the tests or documentation needed to support that change; and
- no personal data, source documents, generated local workspace files, passwords, or
  unrelated formatting changes.

Write the first line as a short instruction in this pattern:

```text
type: short description of the change
```

Use `fix` for a corrected problem, `feat` for a new user-facing capability, `test` for
test-only work, `docs` for documentation, `ci` for automated checks, and `chore` for
small maintenance work. Good examples are:

```text
fix: preserve annotations when shortening sentences
feat: show selected annotation decisions
docs: add contribution guidance for project owners
ci: run tests for main and develop pull requests
```

Avoid vague messages such as `changes`, `updates`, `fix`, or `work in progress`.
If a change is not ready to describe clearly, keep working locally or open a draft pull
request instead of committing unrelated work together.

## For contributors who run the code

After installing the development environment, run the tests before opening a pull
request:

```bash
python -m pip install -e ".[dev]"
python -m pytest
```

## What reviewers look for

Reviewers check that the contribution:

- addresses a clear problem or user need;
- does not expose research source material or personal data;
- keeps the source evidence and annotation workflow understandable;
- includes or updates tests when behaviour changes; and
- is explained clearly enough for a non-programmer project owner to follow.

For setup and everyday use of HEVA, see the [README](README.md) and the
[tutorial](docs/TUTORIAL.md).

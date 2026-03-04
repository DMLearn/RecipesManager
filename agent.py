"""
Multi-agent PR review workflow for RecipesManager.

This module implements an automated GitHub pull request review system using
a three-agent LlamaIndex workflow:
  - ContextAgent: fetches PR metadata and changed files from the GitHub API
  - CommentorAgent: drafts a structured markdown review comment
  - ReviewAndPostingAgent: validates the draft and posts it to the PR

Required environment variables (set in a .env file or CI secrets):
  GITHUB_TOKEN   - Personal access token with repo read/write permissions
  OPENAI_API_KEY - OpenAI API key for the LLM
  OPENAI_API_BASE - (optional) Custom OpenAI-compatible base URL
  REPOSITORY     - Full GitHub repo URL, e.g. https://github.com/owner/repo
  PR_NUMBER      - The pull request number to review
"""
import asyncio
import os

from dotenv import load_dotenv
from github import Auth, Github
from github.Repository import Repository
from llama_index.core.agent import FunctionAgent
from llama_index.core.workflow import Context
from llama_index.core.agent.workflow import AgentOutput, ToolCallResult, AgentStream, AgentInput, AgentSetup, ToolCall, \
    AgentWorkflow
from llama_index.core.prompts import RichPromptTemplate
from llama_index.core.tools import FunctionTool
from llama_index.llms.openai import OpenAI

# Load environment variables from .env file so secrets are not hard-coded
load_dotenv()

# Target repository and PR to review, sourced from environment variables
# Support for both environment variables and command line arguments for flexibility in CI environments
import sys

def get_config(key, index=None, default=None):
    # Try getting from command line if index is provided
    if index is not None and len(sys.argv) > index:
        return sys.argv[index]
    # Try getting from environment
    return os.getenv(key, default)

github_token = get_config("GITHUB_TOKEN", 1)
repo_name = get_config("REPOSITORY", 2)
pr_number = get_config("PR_NUMBER", 3)
openai_api_key = get_config("OPENAI_API_KEY", 4)
openai_api_base = get_config("OPENAI_API_BASE", 5) or os.getenv("OPENAI_BASE_URL")

# Normalize repo_name to always be owner/repo
if repo_name and "github.com/" in repo_name:
    repo_name = repo_name.split("github.com/")[-1].replace(".git", "")


def get_pr_details(pr_number: int) -> dict:
    """
    Retrieve details about a pull request from the GitHub repository.

    Args:
        pr_number: The pull request number

    Returns:
        A dictionary containing PR details including author (pr.user.login), title, body, diff_url, state, and commit SHAs
    """
    # Initialize GitHub client (using unauthenticated access or set GITHUB_TOKEN env variable)
    g = Github(auth=Auth.Token(github_token))

    try:
        # Get the repository
        repo: Repository = g.get_repo(repo_name)

        # Get the pull request
        pr = repo.get_pull(pr_number)

        # Collect commit SHAs
        commit_shas = [commit.sha for commit in pr.get_commits()]

        # Return PR details with all required properties
        return {
            "author": pr.user.login,
            "title": pr.title,
            "body": pr.body,
            "diff_url": pr.diff_url,
            "state": pr.state,
            "commit_shas": commit_shas,
            "number": pr.number,
            "created_at": str(pr.created_at),
            "updated_at": str(pr.updated_at),
            "merged": pr.merged,
            "url": pr.html_url
        }
    finally:
        g.close()


def get_commit_details(commit_sha: str) -> dict:
    """
    Retrieve details about a specific commit from the GitHub repository.

    Args:
        commit_sha: The commit SHA hash

    Returns:
        A dictionary containing commit details including files changed with their filename, status, additions, deletions, changes, and patch (diff)
    """
    # Initialize GitHub client
    g = Github(auth=Auth.Token(github_token))

    try:
        # Get the repository
        repo: Repository = g.get_repo(repo_name)

        # Get the commit
        commit = repo.get_commit(commit_sha)

        # Collect file details
        files_details = []
        for file in commit.files:
            files_details.append({
                "filename": file.filename,
                "status": file.status,
                "additions": file.additions,
                "deletions": file.deletions,
                "changes": file.changes,
                "patch": file.patch if file.patch else ""
            })

        return {
            "sha": commit.sha,
            "message": commit.commit.message,
            "author": commit.commit.author.name,
            "files": files_details
        }
    finally:
        g.close()


def get_file_content(file_path: str) -> str:
    """
    Retrieve the content of a specific file from the GitHub repository.

    Args:
        file_path: The path to the file in the repository (e.g., 'pytest.ini')

    Returns:
        The content of the file as a string.
    """
    g = Github(auth=Auth.Token(github_token))

    try:
        # Get the repository
        repo: Repository = g.get_repo(repo_name)

        # Get the file content
        content_file = repo.get_contents(file_path)

        # If it's a directory, return a message
        if isinstance(content_file, list):
            return f"Error: '{file_path}' is a directory, not a file."

        # Return decoded content
        return content_file.decoded_content.decode("utf-8")
    except Exception as e:
        return f"Error retrieving file content: {str(e)}"
    finally:
        g.close()


async def store_context_state(ctx: Context, key: str, value) -> str:
    """
    Store context data in the shared state for later retrieval by other agents.

    Args:
        ctx: Workflow context
        key: A unique identifier for the context (e.g., 'pr_2_context')
        value: Dictionary containing the context information to store

    Returns:
        A confirmation message indicating the context was stored successfully.
    """
    state = await ctx.store.get("data", default={})
    if not isinstance(state, dict):
        state = {}
    state[key] = value
    await ctx.store.set("data", state)
    return f"Context stored successfully with key: {key}"


async def retrieve_context_state(ctx: Context, key: str) -> dict:
    """
    Retrieve previously stored context data from the shared state.

    Args:
        ctx: Workflow context
        key: The unique identifier for the context to retrieve

    Returns:
        The stored context data dictionary, or an error message if not found.
    """
    state = await ctx.store.get("data", default={})
    if key in state:
        return state[key]
    return {"error": f"No context found for key: {key}"}


async def submit_draft_review(ctx: Context, draft_review: str) -> str:
    """
    Submit the completed draft review for approval and posting.
    Call this tool once you have written the full review text.

    Args:
        ctx: Workflow context
        draft_review: The complete review text in markdown format

    Returns:
        Confirmation and instruction to hand off to ReviewAndPostingAgent.
    """
    state = await ctx.store.get("data", default={})
    if not isinstance(state, dict):
        state = {}
    state["draft_review"] = draft_review
    await ctx.store.set("data", state)
    return "Draft review saved. You MUST now hand off to ReviewAndPostingAgent to post it."


# ---------------------------------------------------------------------------
# Tool definitions — wrap plain Python functions as LlamaIndex FunctionTools
# so agents can call them during the workflow.
# ---------------------------------------------------------------------------

pr_details_tool = FunctionTool.from_defaults(
    fn=get_pr_details,
    name="get_pr_details",
    description="Retrieve details about a pull request from the GitHub repository given the PR number. Returns author (pr.user.login), title, body, diff_url, state, and commit SHAs."
)

commit_details_tool = FunctionTool.from_defaults(
    fn=get_commit_details,
    name="get_commit_details",
    description="Retrieve details about a specific commit from the GitHub repository given the commit SHA. Returns commit message, author, and file details including filename, status, additions, deletions, changes, and patch (diff)."
)

file_content_tool = FunctionTool.from_defaults(
    fn=get_file_content,
    name="get_file_content",
    description="Retrieve the content of a specific file from the GitHub repository given the file path. Useful for reading configuration files, source code, or documentation."
)


def get_changed_files(commit_sha: str) -> list:
    """
    Retrieve the list of files changed in a specific commit.

    Args:
        commit_sha: The commit SHA hash

    Returns:
        A list of dicts, each containing filename, status, additions, deletions, changes, and patch.
    """
    details = get_commit_details(commit_sha)
    return details.get("files", [])


changed_files_tool = FunctionTool.from_defaults(
    fn=get_changed_files,
    name="get_changed_files",
    description="Retrieve the list of files changed in a specific commit given the commit SHA. Returns a list of file dicts with filename, status, additions, deletions, changes, and patch."
)

store_context_state_tool = FunctionTool.from_defaults(
    fn=store_context_state,
    name="store_context_state",
    description="Store context data in the workflow state for later retrieval by other agents. Use a descriptive key like 'pr_<number>_context' and provide all gathered information as a dictionary."
)

retrieve_context_state_tool = FunctionTool.from_defaults(
    fn=retrieve_context_state,
    name="retrieve_context_state",
    description="Retrieve previously stored context data from the workflow state using the context key."
)

submit_draft_review_tool = FunctionTool.from_defaults(
    fn=submit_draft_review,
    name="submit_draft_review",
    description="Submit your completed review draft for approval and posting. Pass the full review text as draft_review. Call this once your review is ready."
)


def post_review_to_github(pr_number: int, comment: str) -> str:
    """
    Post a review comment to a GitHub pull request.

    Args:
        pr_number: The pull request number
        comment: The review comment to post

    Returns:
        A confirmation message indicating the review was posted successfully.
    """
    g = Github(auth=Auth.Token(github_token))

    try:
        # Get the repository
        repo: Repository = g.get_repo(repo_name)

        # Get the pull request
        pr = repo.get_pull(pr_number)

        # Create the review
        pr.create_review(body=comment)

        return f"Review posted successfully to PR #{pr_number}"
    except Exception as e:
        return f"Error posting review: {str(e)}"
    finally:
        g.close()


post_review_tool = FunctionTool.from_defaults(
    fn=post_review_to_github,
    name="post_review_to_github",
    description="Post a review comment to a GitHub pull request. Takes the PR number and the comment text."
)

# ---------------------------------------------------------------------------
# LLM and agent definitions
# ---------------------------------------------------------------------------

# Shared LLM instance used by all three agents
llm = OpenAI(model="gpt-4o-mini", api_key=openai_api_key, base_url=openai_api_base)

# ContextAgent: responsible for gathering all PR information from GitHub
context_agent = FunctionAgent(
    tools=[pr_details_tool, commit_details_tool, changed_files_tool, file_content_tool, store_context_state_tool],
    llm=llm,
    verbose=True,
    can_handoff_to=["CommentorAgent"],
    name="ContextAgent",
    description="Uses the GitHub API to retrieve context for a pull request.",
    system_prompt="""You are the context gathering agent. When gathering context, you MUST gather 
: 
    - The details: author, title, body, diff_url, state, and head_sha; 

    - Changed files; 

    - Any requested for files; 

After gathering all the context, you MUST store it using the store_context_state tool with a key like 'pr_<number>_context' 
so that other agents (like CommentorAgent) can retrieve and use it later.
"""
)

# CommentorAgent: drafts the review comment using context gathered by ContextAgent
commentor_agent = FunctionAgent(
    tools=[retrieve_context_state_tool, submit_draft_review_tool],
    llm=llm,
    verbose=True,
    can_handoff_to=["ContextAgent", "ReviewAndPostingAgent"],
    name="CommentorAgent",
    description="Uses the context gathered by the ContextAgent to draft a pull request review comment.",
    system_prompt="""You are the commentor agent that writes review comments for pull requests.

You have exactly two tools: retrieve_context_state and submit_draft_review.

Step 1: Call retrieve_context_state with key 'pr_<number>_context' to load the PR details.
  - If the result contains an error, hand off to ContextAgent to gather context first.

Step 2: Compose a ~200-300 word review in markdown covering:
  - What is good about the PR
  - Whether the author followed ALL contribution rules (what is missing?)
  - Whether there are tests for new functionality, and migrations for new models
  - Whether new endpoints are documented
  - Specific lines that could be improved (quote them, offer suggestions)
  - Address the author directly (e.g. "Thanks for this. Could you also fix X?")

Step 3: Call submit_draft_review with the complete review text as the draft_review argument.
  Do NOT output the review as a text response — pass it to the tool.

Step 4: After submit_draft_review returns, hand off to ReviewAndPostingAgent.
"""
)

# ReviewAndPostingAgent: validates the draft review and posts it to GitHub
review_agent = FunctionAgent(
    tools=[retrieve_context_state_tool, post_review_tool],
    llm=llm,
    verbose=True,
    can_handoff_to=["CommentorAgent"],
    name="ReviewAndPostingAgent",
    description="Retrieves the draft review from state and posts it to GitHub after a quality check.",
    system_prompt="""You are the Review and Posting agent.

Step 1: Call retrieve_context_state with key 'draft_review' to get the draft written by CommentorAgent.
  - If no draft is found, hand off to CommentorAgent to write one first.

Step 2: Check that the review meets these criteria:
  - ~200-300 words in markdown format
  - States what is good about the PR
  - Mentions contribution rule compliance
  - Addresses test coverage and migrations
  - Addresses endpoint documentation
  - Includes quoted lines with improvement suggestions

Step 3: If the review meets all criteria, call post_review_to_github with the PR number and review text.
  If the review is insufficient, hand off to CommentorAgent with specific feedback.

After posting, confirm to the user that the review was posted successfully.
"""
)

# Wire all agents into a single AgentWorkflow. The workflow starts at
# ReviewAndPostingAgent, which will hand off to CommentorAgent or ContextAgent
# as needed.
workflow_agent = AgentWorkflow(
    agents=[context_agent, commentor_agent, review_agent],
    root_agent=review_agent.name,
    initial_state={"data": {}},
)


async def main():
    """Entry point: runs the workflow and streams events to stdout."""
    # Validate required config before starting
    missing = [k for k, v in {"GITHUB_TOKEN": github_token, "REPOSITORY": repo_name,
                               "PR_NUMBER": pr_number, "OPENAI_API_KEY": openai_api_key}.items() if not v]
    if missing:
        print(f"Error: missing required config: {', '.join(missing)}", flush=True)
        sys.exit(1)

    print(f"Starting review for PR #{pr_number} in {repo_name}", flush=True)
    print(f"OpenAI base URL: {openai_api_base}", flush=True)

    # Verify LLM connectivity before running the full workflow
    try:
        test = await llm.acomplete("Reply with OK")
        print(f"LLM connection OK: {test}", flush=True)
    except Exception as e:
        import traceback
        print(f"LLM connection FAILED: {e}", flush=True)
        traceback.print_exc()
        sys.exit(1)

    query = "Write a review for PR: " + str(pr_number)
    prompt = RichPromptTemplate(query)

    handler = workflow_agent.run(prompt.format())

    current_agent = None
    try:
        async for event in handler.stream_events():
            # Print agent transitions so the operator can follow the workflow
            if hasattr(event, "current_agent_name") and event.current_agent_name != current_agent:
                current_agent = event.current_agent_name
                print(f"\n--- Agent: {current_agent} ---", flush=True)
            elif isinstance(event, AgentStream):
                if event.delta:
                    print(event.delta, end="", flush=True)
                if event.thinking_delta:
                    print(event.thinking_delta, end="", flush=True)
            elif isinstance(event, AgentOutput):
                if event.tool_calls:
                    tool_names = [tc.tool_name for tc in event.tool_calls]
                    print(f"Selected tools: {tool_names}", flush=True)
                if event.response.content:
                    print(f"\nFinal response: {event.response.content}", flush=True)
            elif isinstance(event, ToolCall):
                print(f"Calling tool: {event.tool_name}, args: {event.tool_kwargs}", flush=True)
            elif isinstance(event, ToolCallResult):
                print(f"Tool result: {event.tool_output}", flush=True)
    except Exception as e:
        import traceback
        print(f"\nWorkflow error: {e}", flush=True)
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

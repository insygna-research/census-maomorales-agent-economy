"""Sample tasks for testing and demonstration."""

from economy.models import AllocationMethod


# Simple text-based tasks
SIMPLE_TASKS = [
    {
        "title": "Summarize a text",
        "description": "Provide a concise 2-3 sentence summary of the following text about climate change: Climate change refers to long-term shifts in temperatures and weather patterns. These shifts may be natural, but since the 1800s, human activities have been the main driver of climate change, primarily due to burning fossil fuels like coal, oil and gas.",
        "budget_max": 2.0,
        "required_capabilities": ["summarization"],
        "allocation_method": "first_price",
    },
    {
        "title": "Write a haiku",
        "description": "Write a traditional haiku (5-7-5 syllable structure) about the beauty of autumn leaves.",
        "budget_max": 1.5,
        "required_capabilities": ["writing"],
        "allocation_method": "first_price",
    },
    {
        "title": "Translate to Spanish",
        "description": "Translate the following sentence to Spanish: 'The quick brown fox jumps over the lazy dog.'",
        "budget_max": 1.0,
        "required_capabilities": ["translation"],
        "allocation_method": "first_price",
    },
    {
        "title": "Extract key points",
        "description": "Extract 3-5 key points from this product description: Our new smartphone features a 6.7-inch OLED display with 120Hz refresh rate, a triple camera system with 50MP main sensor, 5G connectivity, 8GB RAM, 256GB storage, and an all-day battery that lasts up to 24 hours.",
        "budget_max": 2.5,
        "required_capabilities": ["analysis"],
        "allocation_method": "first_price",
    },
]


# Coding tasks
CODING_TASKS = [
    {
        "title": "Review Python function",
        "description": """Review this Python function for bugs, style issues, and potential improvements:

```python
def calculate_average(numbers):
    total = 0
    for n in numbers:
        total = total + n
    avg = total / len(numbers)
    return avg
```

Provide specific feedback and a corrected version if needed.""",
        "budget_max": 5.0,
        "required_capabilities": ["coding", "review"],
        "allocation_method": "reputation_weighted",
    },
    {
        "title": "Write a sorting function",
        "description": "Write a Python function that implements bubble sort. Include docstring and comments explaining the algorithm. The function should take a list of numbers and return a sorted list.",
        "budget_max": 4.0,
        "required_capabilities": ["coding"],
        "allocation_method": "first_price",
    },
    {
        "title": "Debug this code",
        "description": """Find and fix the bug in this Python code:

```python
def find_max(items):
    max_val = 0
    for item in items:
        if item > max_val:
            max_val = item
    return max_val

# This returns 0 when called with [-5, -3, -10]
```

Explain the bug and provide the corrected code.""",
        "budget_max": 3.0,
        "required_capabilities": ["coding", "debugging"],
        "allocation_method": "first_price",
    },
]


# Research tasks (including web search)
RESEARCH_TASKS = [
    {
        "title": "Research latest AI developments",
        "description": "Search the web and provide a summary of the 3 most significant AI developments in the past month. Include links to sources if possible.",
        "budget_max": 8.0,
        "required_capabilities": ["web_search", "research"],
        "inputs": {"query": "latest AI developments news 2024"},
        "allocation_method": "reputation_weighted",
    },
    {
        "title": "Find Python library for data visualization",
        "description": "Search for and recommend the best Python library for creating interactive data visualizations for web applications. Compare at least 3 options.",
        "budget_max": 5.0,
        "required_capabilities": ["web_search", "research"],
        "inputs": {"search_query": "best Python interactive data visualization library"},
        "allocation_method": "first_price",
    },
    {
        "title": "Explain quantum computing basics",
        "description": "Write a beginner-friendly explanation of quantum computing. Cover what qubits are, how they differ from classical bits, and give one practical application example.",
        "budget_max": 6.0,
        "required_capabilities": ["research", "writing"],
        "allocation_method": "first_price",
    },
]


# Complex multi-step tasks (good for manager agents)
COMPLEX_TASKS = [
    {
        "title": "Create a project proposal",
        "description": """Create a brief project proposal for a mobile app that helps users track their water intake. Include:
1. Problem statement (why this app is needed)
2. Key features (3-5 core features)
3. Technical requirements (platform, tech stack suggestions)
4. Success metrics (how to measure if the app is successful)

Format as a structured document with clear sections.""",
        "budget_max": 15.0,
        "required_capabilities": ["writing", "analysis", "research"],
        "allocation_method": "reputation_weighted",
    },
    {
        "title": "Analyze and improve code architecture",
        "description": """Given this simple e-commerce order system, analyze the architecture and suggest improvements:

```python
class Order:
    def __init__(self):
        self.items = []
        self.total = 0
        
    def add_item(self, name, price, quantity):
        self.items.append({'name': name, 'price': price, 'qty': quantity})
        self.total += price * quantity
        
    def checkout(self, payment_method, address):
        # Process payment
        print(f"Charging {self.total} via {payment_method}")
        # Send to shipping
        print(f"Shipping to {address}")
        # Send email
        print("Sending confirmation email")
        return True
```

Identify at least 3 design issues and provide refactored code with explanations.""",
        "budget_max": 12.0,
        "required_capabilities": ["coding", "review", "analysis"],
        "allocation_method": "reputation_weighted",
    },
]


# All tasks combined
ALL_TASKS = SIMPLE_TASKS + CODING_TASKS + RESEARCH_TASKS + COMPLEX_TASKS


def get_task_by_capability(capability: str) -> list[dict]:
    """Get tasks that require a specific capability."""
    return [
        t for t in ALL_TASKS
        if capability in t.get("required_capabilities", [])
    ]


def get_task_by_budget(min_budget: float = 0, max_budget: float = float("inf")) -> list[dict]:
    """Get tasks within a budget range."""
    return [
        t for t in ALL_TASKS
        if min_budget <= t["budget_max"] <= max_budget
    ]


async def publish_sample_tasks(client, task_list: list[dict] | None = None):
    """Publish sample tasks to the market."""
    tasks = task_list or SIMPLE_TASKS[:3]
    published = []
    
    for task_data in tasks:
        task = await client.publish_task(
            title=task_data["title"],
            description=task_data["description"],
            budget_max=task_data["budget_max"],
            required_capabilities=task_data.get("required_capabilities", []),
            inputs=task_data.get("inputs", {}),
            allocation_method=task_data.get("allocation_method", "first_price"),
        )
        published.append(task)
    
    return published

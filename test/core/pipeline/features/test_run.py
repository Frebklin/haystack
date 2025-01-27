from typing import List, Optional, Dict, Any

from pytest_bdd import scenarios, given
import pytest

from haystack import Pipeline, Document, component
from haystack.dataclasses import ChatMessage, GeneratedAnswer
from haystack.components.routers import ConditionalRouter
from haystack.components.builders import PromptBuilder, AnswerBuilder
from haystack.components.retrievers.in_memory import InMemoryBM25Retriever
from haystack.document_stores.in_memory import InMemoryDocumentStore
from haystack.components.others import Multiplexer
from haystack.core.errors import PipelineMaxLoops, PipelineRuntimeError
from haystack.testing.sample_components import (
    Accumulate,
    AddFixedValue,
    Double,
    Greet,
    Parity,
    Repeat,
    Subtract,
    Sum,
    Threshold,
    Remainder,
    FString,
    Hello,
    TextSplitter,
    StringListJoiner,
    SelfLoop,
)
from haystack.testing.factory import component_class


pytestmark = pytest.mark.integration

scenarios("pipeline_run.feature")


@given("a pipeline that has no components", target_fixture="pipeline_data")
def pipeline_that_has_no_components():
    pipeline = Pipeline()
    inputs = {}
    expected_outputs = {}
    return pipeline, inputs, expected_outputs, []


@given("a pipeline that is linear", target_fixture="pipeline_data")
def pipeline_that_is_linear():
    pipeline = Pipeline()
    pipeline.add_component("first_addition", AddFixedValue(add=2))
    pipeline.add_component("second_addition", AddFixedValue())
    pipeline.add_component("double", Double())
    pipeline.connect("first_addition", "double")
    pipeline.connect("double", "second_addition")

    return (
        pipeline,
        {"first_addition": {"value": 1}},
        {"second_addition": {"result": 7}},
        ["first_addition", "double", "second_addition"],
    )


@given("a pipeline that has an infinite loop", target_fixture="pipeline_data")
def pipeline_that_has_an_infinite_loop():
    def custom_init(self):
        component.set_input_type(self, "x", int)
        component.set_input_type(self, "y", int, 1)
        component.set_output_types(self, a=int, b=int)

    FakeComponent = component_class("FakeComponent", output={"a": 1, "b": 1}, extra_fields={"__init__": custom_init})
    pipe = Pipeline(max_loops_allowed=1)
    pipe.add_component("first", FakeComponent())
    pipe.add_component("second", FakeComponent())
    pipe.connect("first.a", "second.x")
    pipe.connect("second.b", "first.y")
    return pipe, {"first": {"x": 1}}, PipelineMaxLoops


@given("a pipeline that is really complex with lots of components, forks, and loops", target_fixture="pipeline_data")
def pipeline_complex():
    pipeline = Pipeline(max_loops_allowed=2)
    pipeline.add_component("greet_first", Greet(message="Hello, the value is {value}."))
    pipeline.add_component("accumulate_1", Accumulate())
    pipeline.add_component("add_two", AddFixedValue(add=2))
    pipeline.add_component("parity", Parity())
    pipeline.add_component("add_one", AddFixedValue(add=1))
    pipeline.add_component("accumulate_2", Accumulate())

    pipeline.add_component("multiplexer", Multiplexer(type_=int))
    pipeline.add_component("below_10", Threshold(threshold=10))
    pipeline.add_component("double", Double())

    pipeline.add_component("greet_again", Greet(message="Hello again, now the value is {value}."))
    pipeline.add_component("sum", Sum())

    pipeline.add_component("greet_enumerator", Greet(message="Hello from enumerator, here the value became {value}."))
    pipeline.add_component("enumerate", Repeat(outputs=["first", "second"]))
    pipeline.add_component("add_three", AddFixedValue(add=3))

    pipeline.add_component("diff", Subtract())
    pipeline.add_component("greet_one_last_time", Greet(message="Bye bye! The value here is {value}!"))
    pipeline.add_component("replicate", Repeat(outputs=["first", "second"]))
    pipeline.add_component("add_five", AddFixedValue(add=5))
    pipeline.add_component("add_four", AddFixedValue(add=4))
    pipeline.add_component("accumulate_3", Accumulate())

    pipeline.connect("greet_first", "accumulate_1")
    pipeline.connect("accumulate_1", "add_two")
    pipeline.connect("add_two", "parity")

    pipeline.connect("parity.even", "greet_again")
    pipeline.connect("greet_again", "sum.values")
    pipeline.connect("sum", "diff.first_value")
    pipeline.connect("diff", "greet_one_last_time")
    pipeline.connect("greet_one_last_time", "replicate")
    pipeline.connect("replicate.first", "add_five.value")
    pipeline.connect("replicate.second", "add_four.value")
    pipeline.connect("add_four", "accumulate_3")

    pipeline.connect("parity.odd", "add_one.value")
    pipeline.connect("add_one", "multiplexer.value")
    pipeline.connect("multiplexer", "below_10")

    pipeline.connect("below_10.below", "double")
    pipeline.connect("double", "multiplexer.value")

    pipeline.connect("below_10.above", "accumulate_2")
    pipeline.connect("accumulate_2", "diff.second_value")

    pipeline.connect("greet_enumerator", "enumerate")
    pipeline.connect("enumerate.second", "sum.values")

    pipeline.connect("enumerate.first", "add_three.value")
    pipeline.connect("add_three", "sum.values")

    return (
        pipeline,
        {"greet_first": {"value": 1}, "greet_enumerator": {"value": 1}},
        {"accumulate_3": {"value": -7}, "add_five": {"result": -6}},
        [
            "greet_first",
            "accumulate_1",
            "add_two",
            "parity",
            "add_one",
            "multiplexer",
            "below_10",
            "double",
            "multiplexer",
            "below_10",
            "double",
            "multiplexer",
            "below_10",
            "accumulate_2",
            "greet_enumerator",
            "enumerate",
            "add_three",
            "sum",
            "diff",
            "greet_one_last_time",
            "replicate",
            "add_five",
            "add_four",
            "accumulate_3",
        ],
    )


@given("a pipeline that has a single component with a default input", target_fixture="pipeline_data")
def pipeline_that_has_a_single_component_with_a_default_input():
    @component
    class WithDefault:
        @component.output_types(b=int)
        def run(self, a: int, b: int = 2):
            return {"c": a + b}

    pipeline = Pipeline()
    pipeline.add_component("with_defaults", WithDefault())

    return (
        pipeline,
        [{"with_defaults": {"a": 40, "b": 30}}, {"with_defaults": {"a": 40}}],
        [{"with_defaults": {"c": 70}}, {"with_defaults": {"c": 42}}],
        [["with_defaults"], ["with_defaults"]],
    )


@given("a pipeline that has two loops of identical lengths", target_fixture="pipeline_data")
def pipeline_that_has_two_loops_of_identical_lengths():
    pipeline = Pipeline(max_loops_allowed=10)
    pipeline.add_component("multiplexer", Multiplexer(type_=int))
    pipeline.add_component("remainder", Remainder(divisor=3))
    pipeline.add_component("add_one", AddFixedValue(add=1))
    pipeline.add_component("add_two", AddFixedValue(add=2))

    pipeline.connect("multiplexer.value", "remainder.value")
    pipeline.connect("remainder.remainder_is_1", "add_two.value")
    pipeline.connect("remainder.remainder_is_2", "add_one.value")
    pipeline.connect("add_two", "multiplexer.value")
    pipeline.connect("add_one", "multiplexer.value")

    return (
        pipeline,
        [
            {"multiplexer": {"value": 0}},
            {"multiplexer": {"value": 3}},
            {"multiplexer": {"value": 4}},
            {"multiplexer": {"value": 5}},
            {"multiplexer": {"value": 6}},
        ],
        [
            {"remainder": {"remainder_is_0": 0}},
            {"remainder": {"remainder_is_0": 3}},
            {"remainder": {"remainder_is_0": 6}},
            {"remainder": {"remainder_is_0": 6}},
            {"remainder": {"remainder_is_0": 6}},
        ],
        [
            ["multiplexer", "remainder"],
            ["multiplexer", "remainder"],
            ["multiplexer", "remainder", "add_two", "multiplexer", "remainder"],
            ["multiplexer", "remainder", "add_one", "multiplexer", "remainder"],
            ["multiplexer", "remainder"],
        ],
    )


@given("a pipeline that has two loops of different lengths", target_fixture="pipeline_data")
def pipeline_that_has_two_loops_of_different_lengths():
    pipeline = Pipeline(max_loops_allowed=10)
    pipeline.add_component("multiplexer", Multiplexer(type_=int))
    pipeline.add_component("remainder", Remainder(divisor=3))
    pipeline.add_component("add_one", AddFixedValue(add=1))
    pipeline.add_component("add_two_1", AddFixedValue(add=1))
    pipeline.add_component("add_two_2", AddFixedValue(add=1))

    pipeline.connect("multiplexer.value", "remainder.value")
    pipeline.connect("remainder.remainder_is_1", "add_two_1.value")
    pipeline.connect("add_two_1", "add_two_2.value")
    pipeline.connect("add_two_2", "multiplexer")
    pipeline.connect("remainder.remainder_is_2", "add_one.value")
    pipeline.connect("add_one", "multiplexer")

    return (
        pipeline,
        [
            {"multiplexer": {"value": 0}},
            {"multiplexer": {"value": 3}},
            {"multiplexer": {"value": 4}},
            {"multiplexer": {"value": 5}},
            {"multiplexer": {"value": 6}},
        ],
        [
            {"remainder": {"remainder_is_0": 0}},
            {"remainder": {"remainder_is_0": 3}},
            {"remainder": {"remainder_is_0": 6}},
            {"remainder": {"remainder_is_0": 6}},
            {"remainder": {"remainder_is_0": 6}},
        ],
        [
            ["multiplexer", "remainder"],
            ["multiplexer", "remainder"],
            ["multiplexer", "remainder", "add_two_1", "add_two_2", "multiplexer", "remainder"],
            ["multiplexer", "remainder", "add_one", "multiplexer", "remainder"],
            ["multiplexer", "remainder"],
        ],
    )


@given("a pipeline that has a single loop with two conditional branches", target_fixture="pipeline_data")
def pipeline_that_has_a_single_loop_with_two_conditional_branches():
    accumulator = Accumulate()
    pipeline = Pipeline(max_loops_allowed=10)

    pipeline.add_component("add_one", AddFixedValue(add=1))
    pipeline.add_component("multiplexer", Multiplexer(type_=int))
    pipeline.add_component("below_10", Threshold(threshold=10))
    pipeline.add_component("below_5", Threshold(threshold=5))
    pipeline.add_component("add_three", AddFixedValue(add=3))
    pipeline.add_component("accumulator", accumulator)
    pipeline.add_component("add_two", AddFixedValue(add=2))

    pipeline.connect("add_one.result", "multiplexer")
    pipeline.connect("multiplexer.value", "below_10.value")
    pipeline.connect("below_10.below", "accumulator.value")
    pipeline.connect("accumulator.value", "below_5.value")
    pipeline.connect("below_5.above", "add_three.value")
    pipeline.connect("below_5.below", "multiplexer")
    pipeline.connect("add_three.result", "multiplexer")
    pipeline.connect("below_10.above", "add_two.value")

    return (
        pipeline,
        {"add_one": {"value": 3}},
        {"add_two": {"result": 13}},
        [
            "add_one",
            "multiplexer",
            "below_10",
            "accumulator",
            "below_5",
            "multiplexer",
            "below_10",
            "accumulator",
            "below_5",
            "add_three",
            "multiplexer",
            "below_10",
            "add_two",
        ],
    )


@given("a pipeline that has a component with dynamic inputs defined in init", target_fixture="pipeline_data")
def pipeline_that_has_a_component_with_dynamic_inputs_defined_in_init():
    pipeline = Pipeline()
    pipeline.add_component("hello", Hello())
    pipeline.add_component("fstring", FString(template="This is the greeting: {greeting}!", variables=["greeting"]))
    pipeline.add_component("splitter", TextSplitter())
    pipeline.connect("hello.output", "fstring.greeting")
    pipeline.connect("fstring.string", "splitter.sentence")

    return (
        pipeline,
        [{"hello": {"word": "Alice"}}, {"hello": {"word": "Alice"}, "fstring": {"template": "Received: {greeting}"}}],
        [
            {"splitter": {"output": ["This", "is", "the", "greeting:", "Hello,", "Alice!!"]}},
            {"splitter": {"output": ["Received:", "Hello,", "Alice!"]}},
        ],
        [["hello", "fstring", "splitter"], ["hello", "fstring", "splitter"]],
    )


@given("a pipeline that has two branches that don't merge", target_fixture="pipeline_data")
def pipeline_that_has_two_branches_that_dont_merge():
    pipeline = Pipeline()
    pipeline.add_component("add_one", AddFixedValue(add=1))
    pipeline.add_component("parity", Parity())
    pipeline.add_component("add_ten", AddFixedValue(add=10))
    pipeline.add_component("double", Double())
    pipeline.add_component("add_three", AddFixedValue(add=3))

    pipeline.connect("add_one.result", "parity.value")
    pipeline.connect("parity.even", "add_ten.value")
    pipeline.connect("parity.odd", "double.value")
    pipeline.connect("add_ten.result", "add_three.value")

    return (
        pipeline,
        [{"add_one": {"value": 1}}, {"add_one": {"value": 2}}],
        [{"add_three": {"result": 15}}, {"double": {"value": 6}}],
        [["add_one", "parity", "add_ten", "add_three"], ["add_one", "parity", "double"]],
    )


@given("a pipeline that has three branches that don't merge", target_fixture="pipeline_data")
def pipeline_that_has_three_branches_that_dont_merge():
    pipeline = Pipeline()
    pipeline.add_component("add_one", AddFixedValue(add=1))
    pipeline.add_component("repeat", Repeat(outputs=["first", "second"]))
    pipeline.add_component("add_ten", AddFixedValue(add=10))
    pipeline.add_component("double", Double())
    pipeline.add_component("add_three", AddFixedValue(add=3))
    pipeline.add_component("add_one_again", AddFixedValue(add=1))

    pipeline.connect("add_one.result", "repeat.value")
    pipeline.connect("repeat.first", "add_ten.value")
    pipeline.connect("repeat.second", "double.value")
    pipeline.connect("repeat.second", "add_three.value")
    pipeline.connect("add_three.result", "add_one_again.value")

    return (
        pipeline,
        {"add_one": {"value": 1}},
        {"add_one_again": {"result": 6}, "add_ten": {"result": 12}, "double": {"value": 4}},
        ["add_one", "repeat", "double", "add_ten", "add_three", "add_one_again"],
    )


@given("a pipeline that has two branches that merge", target_fixture="pipeline_data")
def pipeline_that_has_two_branches_that_merge():
    pipeline = Pipeline()
    pipeline.add_component("first_addition", AddFixedValue(add=2))
    pipeline.add_component("second_addition", AddFixedValue(add=2))
    pipeline.add_component("third_addition", AddFixedValue(add=2))
    pipeline.add_component("diff", Subtract())
    pipeline.add_component("fourth_addition", AddFixedValue(add=1))

    pipeline.connect("first_addition.result", "second_addition.value")
    pipeline.connect("second_addition.result", "diff.first_value")
    pipeline.connect("third_addition.result", "diff.second_value")
    pipeline.connect("diff", "fourth_addition.value")
    return (
        pipeline,
        {"first_addition": {"value": 1}, "third_addition": {"value": 1}},
        {"fourth_addition": {"result": 3}},
        ["first_addition", "second_addition", "third_addition", "diff", "fourth_addition"],
    )


@given(
    "a pipeline that has different combinations of branches that merge and do not merge", target_fixture="pipeline_data"
)
def pipeline_that_has_different_combinations_of_branches_that_merge_and_do_not_merge():
    pipeline = Pipeline()
    pipeline.add_component("add_one", AddFixedValue())
    pipeline.add_component("parity", Parity())
    pipeline.add_component("add_ten", AddFixedValue(add=10))
    pipeline.add_component("double", Double())
    pipeline.add_component("add_four", AddFixedValue(add=4))
    pipeline.add_component("add_two", AddFixedValue())
    pipeline.add_component("add_two_as_well", AddFixedValue())
    pipeline.add_component("diff", Subtract())

    pipeline.connect("add_one.result", "parity.value")
    pipeline.connect("parity.even", "add_four.value")
    pipeline.connect("parity.odd", "double.value")
    pipeline.connect("add_ten.result", "diff.first_value")
    pipeline.connect("double.value", "diff.second_value")
    pipeline.connect("parity.odd", "add_ten.value")
    pipeline.connect("add_four.result", "add_two.value")
    pipeline.connect("add_four.result", "add_two_as_well.value")

    return (
        pipeline,
        [
            {"add_one": {"value": 1}, "add_two": {"add": 2}, "add_two_as_well": {"add": 2}},
            {"add_one": {"value": 2}, "add_two": {"add": 2}, "add_two_as_well": {"add": 2}},
        ],
        [{"add_two": {"result": 8}, "add_two_as_well": {"result": 8}}, {"diff": {"difference": 7}}],
        [
            ["add_one", "parity", "add_four", "add_two", "add_two_as_well"],
            ["add_one", "parity", "double", "add_ten", "diff"],
        ],
    )


@given("a pipeline that has two branches, one of which loops back", target_fixture="pipeline_data")
def pipeline_that_has_two_branches_one_of_which_loops_back():
    pipeline = Pipeline(max_loops_allowed=10)
    pipeline.add_component("add_zero", AddFixedValue(add=0))
    pipeline.add_component("multiplexer", Multiplexer(type_=int))
    pipeline.add_component("sum", Sum())
    pipeline.add_component("below_10", Threshold(threshold=10))
    pipeline.add_component("add_one", AddFixedValue(add=1))
    pipeline.add_component("counter", Accumulate())
    pipeline.add_component("add_two", AddFixedValue(add=2))

    pipeline.connect("add_zero", "multiplexer.value")
    pipeline.connect("multiplexer", "below_10.value")
    pipeline.connect("below_10.below", "add_one.value")
    pipeline.connect("add_one.result", "counter.value")
    pipeline.connect("counter.value", "multiplexer.value")
    pipeline.connect("below_10.above", "add_two.value")
    pipeline.connect("add_two.result", "sum.values")

    return (
        pipeline,
        {"add_zero": {"value": 8}, "sum": {"values": 2}},
        {"sum": {"total": 23}},
        [
            "add_zero",
            "multiplexer",
            "below_10",
            "add_one",
            "counter",
            "multiplexer",
            "below_10",
            "add_one",
            "counter",
            "multiplexer",
            "below_10",
            "add_two",
            "sum",
        ],
    )


@given("a pipeline that has a component with mutable input", target_fixture="pipeline_data")
def pipeline_that_has_a_component_with_mutable_input():
    @component
    class InputMangler:
        @component.output_types(mangled_list=List[str])
        def run(self, input_list: List[str]):
            input_list.append("extra_item")
            return {"mangled_list": input_list}

    pipe = Pipeline()
    pipe.add_component("mangler1", InputMangler())
    pipe.add_component("mangler2", InputMangler())
    pipe.add_component("concat1", StringListJoiner())
    pipe.add_component("concat2", StringListJoiner())
    pipe.connect("mangler1", "concat1")
    pipe.connect("mangler2", "concat2")

    input_list = ["foo", "bar"]

    return (
        pipe,
        {"mangler1": {"input_list": input_list}, "mangler2": {"input_list": input_list}},
        {"concat1": {"output": ["foo", "bar", "extra_item"]}, "concat2": {"output": ["foo", "bar", "extra_item"]}},
        ["mangler1", "mangler2", "concat1", "concat2"],
    )


@given("a pipeline that has a component with mutable output sent to multiple inputs", target_fixture="pipeline_data")
def pipeline_that_has_a_component_with_mutable_output_sent_to_multiple_inputs():
    @component
    class PassThroughPromptBuilder:
        # This is a pass-through component that returns the same input
        @component.output_types(prompt=List[ChatMessage])
        def run(self, prompt_source: List[ChatMessage]):
            return {"prompt": prompt_source}

    @component
    class MessageMerger:
        @component.output_types(merged_message=str)
        def run(self, messages: List[ChatMessage], metadata: dict = None):
            return {"merged_message": "\n".join(t.content for t in messages)}

    @component
    class FakeGenerator:
        # This component is a fake generator that always returns the same message
        @component.output_types(replies=List[ChatMessage])
        def run(self, messages: List[ChatMessage]):
            return {"replies": [ChatMessage.from_assistant("Fake message")]}

    prompt_builder = PassThroughPromptBuilder()
    llm = FakeGenerator()
    mm1 = MessageMerger()
    mm2 = MessageMerger()

    pipe = Pipeline()
    pipe.add_component("prompt_builder", prompt_builder)
    pipe.add_component("llm", llm)
    pipe.add_component("mm1", mm1)
    pipe.add_component("mm2", mm2)

    pipe.connect("prompt_builder.prompt", "llm.messages")
    pipe.connect("prompt_builder.prompt", "mm1")
    pipe.connect("llm.replies", "mm2")

    messages = [
        ChatMessage.from_system("Always respond in English even if some input data is in other languages."),
        ChatMessage.from_user("Tell me about Berlin"),
    ]
    params = {"metadata": {"metadata_key": "metadata_value", "meta2": "value2"}}

    return (
        pipe,
        {"prompt_builder": {"prompt_source": messages}, "mm1": params, "mm2": params},
        {
            "mm1": {
                "merged_message": "Always respond in English even if some input data is in other languages.\nTell me about Berlin"
            },
            "mm2": {"merged_message": "Fake message"},
        },
        ["prompt_builder", "mm1", "llm", "mm2"],
    )


@given(
    "a pipeline that has a greedy and variadic component after a component with default input",
    target_fixture="pipeline_data",
)
def pipeline_that_has_a_greedy_and_variadic_component_after_a_component_with_default_input():
    """
    This test verifies that `Pipeline.run()` executes the components in the correct order when
    there's a greedy Component with variadic input right before a Component with at least one default input.

    We use the `spying_tracer` fixture to simplify the code to verify the order of execution.
    This creates some coupling between this test and how we trace the Pipeline execution.
    A worthy tradeoff in my opinion, we will notice right away if we change either the run logic or
    the tracing logic.
    """
    document_store = InMemoryDocumentStore()
    document_store.write_documents([Document(content="This is a simple document")])

    pipeline = Pipeline()
    template = "Given this documents: {{ documents|join(', ', attribute='content') }} Answer this question: {{ query }}"
    pipeline.add_component("retriever", InMemoryBM25Retriever(document_store=document_store))
    pipeline.add_component("prompt_builder", PromptBuilder(template=template))
    pipeline.add_component("multiplexer", Multiplexer(List[Document]))

    pipeline.connect("retriever", "multiplexer")
    pipeline.connect("multiplexer", "prompt_builder.documents")
    return (
        pipeline,
        {"query": "This is my question"},
        {
            "prompt_builder": {
                "prompt": "Given this documents: This is a simple document Answer this question: This is my question"
            }
        },
        ["retriever", "multiplexer", "prompt_builder"],
    )


@given("a pipeline that has a component that doesn't return a dictionary", target_fixture="pipeline_data")
def pipeline_that_has_a_component_that_doesnt_return_a_dictionary():
    BrokenComponent = component_class(
        "BrokenComponent", input_types={"a": int}, output_types={"b": int}, output=1  # type:ignore
    )

    pipe = Pipeline(max_loops_allowed=10)
    pipe.add_component("comp", BrokenComponent())
    return pipe, {"comp": {"a": 1}}, PipelineRuntimeError


@given(
    "a pipeline that has components added in a different order from the order of execution",
    target_fixture="pipeline_data",
)
def pipeline_that_has_components_added_in_a_different_order_from_the_order_of_execution():
    """
    We enqueue the Components in internal `to_run` data structure at the start of `Pipeline.run()` using the order
    they are added in the Pipeline with `Pipeline.add_component()`.
    If a Component A with defaults is added before a Component B that has no defaults, but in the Pipeline
    logic A must be executed after B it could run instead before.

    This test verifies that the order of execution is correct.
    """
    docs = [Document(content="Rome is the capital of Italy"), Document(content="Paris is the capital of France")]
    doc_store = InMemoryDocumentStore()
    doc_store.write_documents(docs)
    template = (
        "Given the following information, answer the question.\n"
        "Context:\n"
        "{% for document in documents %}"
        "    {{ document.content }}\n"
        "{% endfor %}"
        "Question: {{ query }}"
    )

    pipe = Pipeline()

    # The order of this addition is important for the test
    # Do not edit them.
    pipe.add_component("prompt_builder", PromptBuilder(template=template))
    pipe.add_component("retriever", InMemoryBM25Retriever(document_store=doc_store))
    pipe.connect("retriever", "prompt_builder.documents")

    query = "What is the capital of France?"
    return (
        pipe,
        {"prompt_builder": {"query": query}, "retriever": {"query": query}},
        {
            "prompt_builder": {
                "prompt": "Given the following information, answer the question.\n"
                "Context:\n"
                "    Paris is the capital of France\n"
                "    Rome is the capital of Italy\n"
                "Question: What is the capital of France?"
            }
        },
        ["retriever", "prompt_builder"],
    )


@given("a pipeline that has a component with only default inputs", target_fixture="pipeline_data")
def pipeline_that_has_a_component_with_only_default_inputs():
    FakeGenerator = component_class(
        "FakeGenerator", input_types={"prompt": str}, output_types={"replies": List[str]}, output={"replies": ["Paris"]}
    )
    docs = [Document(content="Rome is the capital of Italy"), Document(content="Paris is the capital of France")]
    doc_store = InMemoryDocumentStore()
    doc_store.write_documents(docs)
    template = (
        "Given the following information, answer the question.\n"
        "Context:\n"
        "{% for document in documents %}"
        "    {{ document.content }}\n"
        "{% endfor %}"
        "Question: {{ query }}"
    )

    pipe = Pipeline()

    pipe.add_component("retriever", InMemoryBM25Retriever(document_store=doc_store))
    pipe.add_component("prompt_builder", PromptBuilder(template=template))
    pipe.add_component("generator", FakeGenerator())
    pipe.add_component("answer_builder", AnswerBuilder())

    pipe.connect("retriever", "prompt_builder.documents")
    pipe.connect("prompt_builder.prompt", "generator.prompt")
    pipe.connect("generator.replies", "answer_builder.replies")
    pipe.connect("retriever.documents", "answer_builder.documents")

    return (
        pipe,
        {"query": "What is the capital of France?"},
        {
            "answer_builder": {
                "answers": [
                    GeneratedAnswer(
                        data="Paris",
                        query="What is the capital of France?",
                        documents=[
                            Document(
                                id="413dccdf51a54cca75b7ed2eddac04e6e58560bd2f0caf4106a3efc023fe3651",
                                content="Paris is the capital of France",
                                score=1.600237583702734,
                            ),
                            Document(
                                id="a4a874fc2ef75015da7924d709fbdd2430e46a8e94add6e0f26cd32c1c03435d",
                                content="Rome is the capital of Italy",
                                score=1.2536639934227616,
                            ),
                        ],
                        meta={},
                    )
                ]
            }
        },
        ["retriever", "prompt_builder", "generator", "answer_builder"],
    )


@given("a pipeline that has a component with only default inputs as first to run", target_fixture="pipeline_data")
def pipeline_that_has_a_component_with_only_default_inputs_as_first_to_run():
    """
    This tests verifies that a Pipeline doesn't get stuck running in a loop if
    it has all the following characterics:
    - The first Component has all defaults for its inputs
    - The first Component receives one input from the user
    - The first Component receives one input from a loop in the Pipeline
    - The second Component has at least one default input
    """

    def fake_generator_run(self, prompt: str, generation_kwargs: Optional[Dict[str, Any]] = None):
        # Simple hack to simulate a model returning a different reply after the
        # the first time it's called
        if getattr(fake_generator_run, "called", False):
            return {"replies": ["Rome"]}
        fake_generator_run.called = True
        return {"replies": ["Paris"]}

    FakeGenerator = component_class(
        "FakeGenerator",
        input_types={"prompt": str, "generation_kwargs": Optional[Dict[str, Any]]},
        output_types={"replies": List[str]},
        extra_fields={"run": fake_generator_run},
    )
    template = (
        "Answer the following question.\n"
        "{% if previous_replies %}\n"
        "Previously you replied incorrectly this:\n"
        "{% for reply in previous_replies %}\n"
        " - {{ reply }}\n"
        "{% endfor %}\n"
        "{% endif %}\n"
        "Question: {{ query }}"
    )
    router = ConditionalRouter(
        routes=[
            {
                "condition": "{{ replies == ['Rome'] }}",
                "output": "{{ replies }}",
                "output_name": "correct_replies",
                "output_type": List[int],
            },
            {
                "condition": "{{ replies == ['Paris'] }}",
                "output": "{{ replies }}",
                "output_name": "incorrect_replies",
                "output_type": List[int],
            },
        ]
    )

    pipe = Pipeline()

    pipe.add_component("prompt_builder", PromptBuilder(template=template))
    pipe.add_component("generator", FakeGenerator())
    pipe.add_component("router", router)

    pipe.connect("prompt_builder.prompt", "generator.prompt")
    pipe.connect("generator.replies", "router.replies")
    pipe.connect("router.incorrect_replies", "prompt_builder.previous_replies")

    return (
        pipe,
        {"prompt_builder": {"query": "What is the capital of Italy?"}},
        {"router": {"correct_replies": ["Rome"]}},
        ["prompt_builder", "generator", "router", "prompt_builder", "generator", "router"],
    )


@given(
    "a pipeline that has only a single component that sends one of its outputs to itself",
    target_fixture="pipeline_data",
)
def pipeline_that_has_a_single_component_that_send_one_of_outputs_to_itself():
    pipeline = Pipeline(max_loops_allowed=10)
    pipeline.add_component("self_loop", SelfLoop())
    pipeline.connect("self_loop.current_value", "self_loop.values")

    return (
        pipeline,
        {"self_loop": {"values": 5}},
        {"self_loop": {"final_result": 0}},
        ["self_loop", "self_loop", "self_loop", "self_loop", "self_loop"],
    )


@given("a pipeline that has a component that sends one of its outputs to itself", target_fixture="pipeline_data")
def pipeline_that_has_a_component_that_sends_one_of_its_outputs_to_itself():
    pipeline = Pipeline(max_loops_allowed=10)
    pipeline.add_component("add_1", AddFixedValue())
    pipeline.add_component("self_loop", SelfLoop())
    pipeline.add_component("add_2", AddFixedValue())
    pipeline.connect("add_1", "self_loop.values")
    pipeline.connect("self_loop.current_value", "self_loop.values")
    pipeline.connect("self_loop.final_result", "add_2.value")

    return (
        pipeline,
        {"add_1": {"value": 5}},
        {"add_2": {"result": 1}},
        ["add_1", "self_loop", "self_loop", "self_loop", "self_loop", "self_loop", "self_loop", "add_2"],
    )


@given(
    "a pipeline that has multiple branches that merge into a component with a single variadic input",
    target_fixture="pipeline_data",
)
def pipeline_that_has_multiple_branches_that_merge_into_a_component_with_a_single_variadic_input():
    pipeline = Pipeline()
    pipeline.add_component("add_one", AddFixedValue())
    pipeline.add_component("parity", Remainder(divisor=2))
    pipeline.add_component("add_ten", AddFixedValue(add=10))
    pipeline.add_component("double", Double())
    pipeline.add_component("add_four", AddFixedValue(add=4))
    pipeline.add_component("add_one_again", AddFixedValue())
    pipeline.add_component("sum", Sum())

    pipeline.connect("add_one.result", "parity.value")
    pipeline.connect("parity.remainder_is_0", "add_ten.value")
    pipeline.connect("parity.remainder_is_1", "double.value")
    pipeline.connect("add_one.result", "sum.values")
    pipeline.connect("add_ten.result", "sum.values")
    pipeline.connect("double.value", "sum.values")
    pipeline.connect("parity.remainder_is_1", "add_four.value")
    pipeline.connect("add_four.result", "add_one_again.value")
    pipeline.connect("add_one_again.result", "sum.values")

    return (
        pipeline,
        [{"add_one": {"value": 1}}, {"add_one": {"value": 2}}],
        [{"sum": {"total": 14}}, {"sum": {"total": 17}}],
        [["add_one", "parity", "add_ten", "sum"], ["add_one", "parity", "double", "add_four", "add_one_again", "sum"]],
    )


@given(
    "a pipeline that has multiple branches of different lengths that merge into a component with a single variadic input",
    target_fixture="pipeline_data",
)
def pipeline_that_has_multiple_branches_of_different_lengths_that_merge_into_a_component_with_a_single_variadic_input():
    pipeline = Pipeline()
    pipeline.add_component("first_addition", AddFixedValue(add=2))
    pipeline.add_component("second_addition", AddFixedValue(add=2))
    pipeline.add_component("third_addition", AddFixedValue(add=2))
    pipeline.add_component("sum", Sum())
    pipeline.add_component("fourth_addition", AddFixedValue(add=1))

    pipeline.connect("first_addition.result", "second_addition.value")
    pipeline.connect("first_addition.result", "sum.values")
    pipeline.connect("second_addition.result", "sum.values")
    pipeline.connect("third_addition.result", "sum.values")
    pipeline.connect("sum.total", "fourth_addition.value")

    return (
        pipeline,
        {"first_addition": {"value": 1}, "third_addition": {"value": 1}},
        {"fourth_addition": {"result": 12}},
        ["first_addition", "second_addition", "third_addition", "sum", "fourth_addition"],
    )

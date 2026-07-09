import streamlit as st


def add_two_numbers(a, b):
    """Return the sum of two numbers."""
    return a + b


st.title("Simple Addition App")

st.write("Enter two numbers and get their sum.")

first_number = st.number_input("First number", value=0.0, format="%f")
second_number = st.number_input("Second number", value=0.0, format="%f")

if st.button("Compute Sum"):
    result = add_two_numbers(first_number, second_number)
    st.success(f"Result: {result}")

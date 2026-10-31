from django.contrib.auth import login
from django.shortcuts import redirect, render

from .forms import SignupForm


def signup(request):
    form = SignupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        login(request, form.save())
        return redirect("/")
    return render(request, "accounts/signup.html", {"form": form})

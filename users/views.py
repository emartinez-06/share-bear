from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from core.models import AIQuote

from .forms import LoginForm, SignupForm


def signup_view(request):
    if request.user.is_authenticated:
        return redirect('home')
    if request.method == 'POST':
        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, f'Welcome to SHARE Bear, {user.first_name or user.username}!')
            return redirect('home')
    else:
        form = SignupForm()
    return render(request, 'users/signup.html', {'form': form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect('home')
    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            user = authenticate(
                request,
                username=form.cleaned_data['username'],
                password=form.cleaned_data['password'],
            )
            if user is not None:
                login(request, user)
                next_url = request.GET.get('next', 'home')
                return redirect(next_url)
            form.add_error(None, 'Invalid username or password.')
    else:
        form = LoginForm()
    return render(request, 'users/login.html', {'form': form})


@require_http_methods(['POST'])
def logout_view(request):
    logout(request)
    return redirect('home')


@login_required
def profile_view(request):
    quotes = AIQuote.objects.filter(user=request.user)[:10]
    return render(request, 'users/profile.html', {'quotes': quotes})

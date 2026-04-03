from django.shortcuts import redirect, render

from .utils import (
    build_comparison_rows,
    check_guess,
    get_all_pokemon_names,
    get_hints,
    get_random_pokemon,
    lookup_pokemon_by_name,
    pokemon_row_to_session_dict,
    sync_pokemon_from_csv,
)


def home(request):
    return render(request, "game/home.html")


def start_game(request):
    filter_type = request.POST.get("filter", "all")
    if filter_type not in ("all", "only_type1"):
        filter_type = "all"

    row = get_random_pokemon(filter_type)
    request.session["pokemon"] = pokemon_row_to_session_dict(row)
    request.session["game_filter"] = filter_type
    request.session["attempts"] = 0
    request.session["last_valid_comparison"] = None

    return redirect("play")


def play(request):
    pokemon = request.session.get("pokemon")
    if not pokemon:
        return redirect("home")

    pokemon = sync_pokemon_from_csv(pokemon)
    request.session["pokemon"] = pokemon

    attempts = request.session.get("attempts", 0)
    game_filter = request.session.get("game_filter", "all")
    single_type_mode = game_filter == "only_type1"

    context = {
        "attempts": attempts,
        "attempts_left": 5 - attempts,
        "single_type_mode": single_type_mode,
        "hints": get_hints(pokemon, attempts, single_type_mode),
        "pokemon_names": get_all_pokemon_names(),
    }

    if request.method == "POST":
        guess = request.POST.get("guess")
        attempts += 1
        request.session["attempts"] = attempts

        is_correct, hints = check_guess(
            guess, pokemon, attempts, single_type_mode
        )
        context["hints"] = hints
        context["attempts"] = attempts
        context["attempts_left"] = 5 - attempts

        if is_correct:
            context["result"] = "win"
            p = sync_pokemon_from_csv(pokemon)
            request.session["pokemon"] = p
            context["pokemon"] = p
            return render(request, "game/result.html", context)

        guessed_row = lookup_pokemon_by_name(guess)
        context["first_invalid_only"] = False
        context["previous_feedback"] = None
        context["comparison_rows"] = None
        context["comparison_error"] = None
        context["guessed_display_name"] = ""

        if guessed_row is None:
            context["comparison_error"] = (
                "This Pokémon is not in the dataset."
            )
            context["guessed_display_name"] = (guess or "").strip()
            if attempts == 1:
                context["first_invalid_only"] = True
            else:
                context["previous_feedback"] = request.session.get(
                    "last_valid_comparison"
                )
        else:
            comparison_rows, _err = build_comparison_rows(guessed_row, pokemon)
            context["comparison_rows"] = comparison_rows
            context["guessed_display_name"] = guessed_row.get("name")
            request.session["last_valid_comparison"] = {
                "rows": comparison_rows,
                "guessed_display_name": guessed_row.get("name"),
            }

        if attempts >= 5:
            context["result"] = "lose"
            p = sync_pokemon_from_csv(pokemon)
            request.session["pokemon"] = p
            context["pokemon"] = p
            return render(request, "game/result.html", context)

    return render(request, "game/play.html", context)

import pygame
import numpy as np

# Inicjalizacja Pygame
pygame.init()

# Wczytanie obrazu mapy
map_image = pygame.image.load('mapa.png')
map_image = pygame.transform.scale(map_image, (800, 600))  # Dopasowanie rozmiaru mapy
map_data = pygame.surfarray.array3d(map_image)

# Funkcja klasyfikująca teren
def is_green_area(color):
    r, g, b = color
    return r > 150 and g > 200 and b > 150

green_map_original = np.array(
    [[is_green_area(map_data[x, y]) for y in range(map_data.shape[1])] for x in range(map_data.shape[0])]
)

green_map = green_map_original.copy()

# Tworzenie początkowego obrazu mapy
output_image = np.zeros_like(map_data)
output_image[green_map] = [0, 100, 0]  # Zielone tereny
output_image[~green_map] = [0, 0, 0] #woda

# Parametry okna
screen = pygame.display.set_mode((1050, 650))
pygame.display.set_caption("Symulacja Pożaru")
clock = pygame.time.Clock()  # Dodany zegar do kontroli FPS

# Parametry wiatru i wilgotności
wind_direction = "Brak"
wind_speed_value = 2
humidity_value = 50

# Przyciski
buttons = {
    "north": pygame.Rect(820, 50, 180, 40),
    "south": pygame.Rect(820, 100, 180, 40),
    "east": pygame.Rect(820, 150, 180, 40),
    "west": pygame.Rect(820, 200, 180, 40),
    "pause": pygame.Rect(820, 400, 180, 40),
    "reset": pygame.Rect(820, 450, 180, 40)
}

# Suwaki
wind_speed_slider = pygame.Rect(820, 500, 180, 10)
humidity_slider = pygame.Rect(820, 550, 180, 10)

# Zmienna kontrolująca pauzę
paused = False

# Dane do śledzenia ognia i wody
fire_start_points = set()
fire_timers = {}
water_zones = {}  # Obszary wody: klucz = (x, y), wartość = czas pozostały do wyschnięcia
WATER_DURATION = 200  # Czas trwania wody w klatkach
CUT_PIXEL_SIZE = 20
WATER_SPREAD_RADIUS = 33  # Maksymalny promień rozlewania wody
cutting_forest = False


# Funkcja gradientu ognia
def get_fire_color(distance):
    if distance == 0:
        return (255, 0, 0)
    elif distance < 3:
        return (255, 255 - distance * 60, 0)
    elif distance < 70:
        return (255, 140 - (distance - 3) * 30, 0)
    elif distance < 150:
        return (150 - (distance - 7) * 50, 0, 0)
    else:
        return None


# Cache kolorów ognia dla lepszej wydajności
FIRE_COLORS = {
    0: (255, 0, 0),
    1: (255, 195, 0),
    2: (255, 135, 0),
    3: (255, 95, 0),
    4: (255, 50, 0),
    5: (255, 20, 0),
    6: (225, 0, 0),
    7: (200, 0, 0),
    8: (150, 0, 0),
    9: (100, 0, 0),
}


# Zoptymalizowana funkcja rozprzestrzeniania ognia
def spread_fire():
    if paused:
        return

    global fire_start_points, output_image
    new_fire_points = set()
    points_to_remove = set()

    # Aktualizacja istniejących punktów ognia
    for (x, y), timer in fire_timers.items():
        fire_timers[(x, y)] = timer + 1
        if timer >= 10:  # Punkt całkowicie się wypalił
            points_to_remove.add((x, y))
            continue

        color = FIRE_COLORS.get(timer)
        if color:
            output_image[x, y] = color

    # Usuwanie wypalonych punktów
    for point in points_to_remove:
        del fire_timers[point]
        if point in fire_start_points:
            fire_start_points.remove(point)

    # Optymalizacja rozprzestrzeniania - sprawdzamy tylko aktywne punkty ognia
    if len(fire_start_points) > 0:
        # Przygotowanie wartości losowych z góry
        random_values = np.random.random(len(fire_start_points) * 4)
        idx = 0

        # Rozprzestrzenianie ognia z użyciem zoptymalizowanej logiki
        for x, y in fire_start_points:
            for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nx, ny = x + dx, y + dy

                if (0 <= nx < map_data.shape[0] and
                        0 <= ny < map_data.shape[1] and
                        green_map[nx, ny] and
                        (nx, ny) not in water_zones and
                        (nx, ny) not in fire_timers):

                    chance = 0.3 * (1 - humidity_value / 100)


                    # Optymalizacja sprawdzania kierunku wiatru
                    if (wind_direction == "North" and dy == -1 or
                            wind_direction == "South" and dy == 1 or
                            wind_direction == "East" and dx == 1 or
                            wind_direction == "West" and dx == -1):
                        chance += wind_speed_value / 10.0

                    if random_values[idx] < chance:
                        new_fire_points.add((nx, ny))
                        green_map[nx, ny] = False
                        fire_timers[(nx, ny)] = 0

                idx = (idx + 1) % len(random_values)

    fire_start_points.update(new_fire_points)

# Funkcja punktowego rozlewania wody
def apply_water(center_x, center_y):
    # Dodaj pierwszy punkt wody
    initial_points = [(center_x, center_y)]
    water_front = set(initial_points)
    processed_points = set()

    # Zwiększone parametry rozlewania
    spread_iterations = 1000  # Zwiększona liczba iteracji
    water_spread_chance = 0.95  # Zwiększona szansa na rozprzestrzenienie
    max_radius = 50  # Maksymalny promień rozprzestrzeniania

    for _ in range(spread_iterations):
        new_water_front = set()

        for water_x, water_y in water_front:
            if (water_x, water_y) in processed_points:
                continue

            # Sprawdź czy punkt jest w zasięgu maksymalnego promienia
            if abs(water_x - center_x) > max_radius or abs(water_y - center_y) > max_radius:
                continue

            # Dodaj wodę w aktualnym punkcie
            if 0 <= water_x < map_data.shape[0] and 0 <= water_y < map_data.shape[1]:
                # Oblicz odległość od centrum
                distance = ((water_x - center_x) ** 2 + (water_y - center_y) ** 2) ** 0.5

                if distance <= max_radius:
                    water_zones[(water_x, water_y)] = WATER_DURATION
                    # Gradient koloru wody - ciemniejszy w centrum, jaśniejszy na brzegach
                    intensity = int(255 * (1 - distance / max_radius))
                    output_image[water_x, water_y] = [0, 0, min(255, intensity + 100)]

                    # Gaś ogień jeśli jest w tym miejscu
                    if (water_x, water_y) in fire_timers:
                        del fire_timers[(water_x, water_y)]
                        if (water_x, water_y) in fire_start_points:
                            fire_start_points.remove((water_x, water_y))

            processed_points.add((water_x, water_y))

            # Sprawdź sąsiednie punkty dla rozlania wody
            for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (-1, -1), (1, -1), (-1, 1)]:
                new_x, new_y = water_x + dx, water_y + dy

                # Sprawdź czy punkt jest w granicach mapy
                if not (0 <= new_x < map_data.shape[0] and 0 <= new_y < map_data.shape[1]):
                    continue

                # Oblicz odległość od centrum dla nowego punktu
                distance = ((new_x - center_x) ** 2 + (new_y - center_y) ** 2) ** 0.5

                # Zmniejsz szansę rozprzestrzeniania wraz z odległością od centrum
                current_spread_chance = water_spread_chance * (1 - distance / max_radius)

                # Rozlej wodę z odpowiednią szansą
                if distance <= max_radius and np.random.random() < current_spread_chance:
                    new_water_front.add((new_x, new_y))

        water_front = new_water_front

        # Zmniejsz szansę na rozprzestrzenianie z każdą iteracją, ale wolniej
        water_spread_chance *= 0.95


# Funkcja rysująca kontrolki
def draw_controls():
    font = pygame.font.Font(None, 25)
    for label, rect in buttons.items():
        pygame.draw.rect(screen, (100, 100, 100), rect)  # Tło przycisków
        screen.blit(font.render(label.capitalize(), True, (255, 255, 255)), (rect.x + 10, rect.y + 10))  # Kolor tekstu
    pygame.draw.rect(screen, (180, 180, 180), wind_speed_slider)
    pygame.draw.rect(screen, (255, 0, 0),
                     pygame.Rect(wind_speed_slider.x + (wind_speed_value - 2) * 20, wind_speed_slider.y, 10, 10))
    pygame.draw.rect(screen, (180, 180, 180), humidity_slider)
    pygame.draw.rect(screen, (0, 0, 255),
                     pygame.Rect(humidity_slider.x + (humidity_value) * 1.5, humidity_slider.y, 10, 10))
    screen.blit(font.render(f"Prędkość wiatru: {wind_speed_value} m/s", True, (0, 0, 0)), (820, 520))
    screen.blit(font.render(f"Wilgotność: {humidity_value}%", True, (0, 0, 0)), (820, 570))
    screen.blit(font.render(f"Kierunek wiatru: {wind_direction}", True, (0, 0, 0)), (820, 250))


# Funkcja obsługująca kliknięcia
def handle_click(mouse_x, mouse_y):
    global wind_direction, wind_speed_value, humidity_value, paused, green_map, fire_start_points, fire_timers
    for label, rect in buttons.items():
        if rect.collidepoint(mouse_x, mouse_y):
            if label in ["north", "south", "east", "west"]:
                wind_direction = label.capitalize()
            elif label == "pause":
                paused = not paused
            elif label == "reset":
                green_map = green_map_original.copy()
                fire_start_points.clear()
                fire_timers.clear()
                global output_image
                output_image = np.zeros_like(map_data)
                output_image[green_map] = [0, 122, 0]
                output_image[~green_map] = [0, 0, 0]
    if wind_speed_slider.collidepoint(mouse_x, mouse_y):
        wind_speed_value = 2 + (mouse_x - wind_speed_slider.x) // 20
        wind_speed_value = max(2, min(wind_speed_value, 16))
    if humidity_slider.collidepoint(mouse_x, mouse_y):
        humidity_value = (mouse_x - humidity_slider.x) // 1.5
        humidity_value = max(0, min(humidity_value, 100))


# Główna pętla gry
running = True
while running:
    clock.tick(60)  # Ograniczenie do 60 FPS

    screen.fill((255, 255, 255))
    screen.blit(map_image, (0, 0))

    output_surface = pygame.surfarray.make_surface(output_image)
    screen.blit(output_surface, (0, 0))
    pygame.draw.rect(screen, (200, 200, 200), (800, 0, 250, 650))  # Szerszy panel boczny
    draw_controls()

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.MOUSEBUTTONDOWN:
            x, y = pygame.mouse.get_pos()
            if x < 800:  # Kliknięcie na mapie
                if cutting_forest:
                    for dx in range(-CUT_PIXEL_SIZE // 2, CUT_PIXEL_SIZE // 2):
                        for dy in range(-CUT_PIXEL_SIZE // 2, CUT_PIXEL_SIZE // 2):
                            nx, ny = x + dx, y + dy
                            if 0 <= nx < map_data.shape[0] and 0 <= ny < map_data.shape[1]:
                                green_map[nx, ny] = False
                                output_image[nx, ny] = [0, 0, 0]
                else:
                    fire_start_points.add((x, y))
                    fire_timers[(x, y)] = 0
            else:  # Kliknięcie na kontrolki
                handle_click(x, y)
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_r:
                cutting_forest = not cutting_forest
            elif event.key == pygame.K_w:  # Zrzut wody
                x, y = pygame.mouse.get_pos()
                if x < 800:
                    apply_water(x, y)

    if not paused:
        spread_fire()

    pygame.display.flip()
pygame.quit()
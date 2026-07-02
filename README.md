## Running the Generator

1. Download the repository.
2. Place the GDMC HTTP Interface mod into your Minecraft `mods` folder.
3. Start Minecraft and create or load a world.
4. Start the GDMC HTTP server.
5. Run the generator:

```bash
python main.py <tribe>
```

Available options:

```text
world      # Generate all four tribes
plains     # Generate only the Plains tribe
desert     # Generate only the Desert tribe
savanna    # Generate only the Savanna tribe
taiga      # Generate only the Taiga tribe
```

Examples:

```bash
python main.py world
python main.py plains
python main.py desert
python main.py savanna
python main.py taiga
```

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches


def parse_timeline_file(filepath: str):
    sections = {}
    color_labels = {}
    current_section = None

    with open(filepath, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("[") and line.endswith("]"):
                current_section = line[1:-1]
                sections[current_section] = []
            elif line.startswith(">"):
                color_key, label = line[1:].split(":", maxsplit=1)
                color_labels[color_key.strip()] = label.strip()
            else:
                try:
                    name, dur, color_key = line.rsplit(",", maxsplit=2)
                    sections[current_section].append((name.strip(), float(dur.strip()), color_key.strip()))
                except ValueError:
                    print(f"Skipping malformed line: {line}")
    return sections, color_labels


def plot_gantt_chart_txt(sections: dict, color_labels: dict):
    fig, ax = plt.subplots(figsize=(12, 0.6 * sum(1 if k.startswith("*") else len(v)+1 for k, v in sections.items())))

    y = 0
    yticks = []
    ylabels = []

    for raw_section, steps in sections.items():
        section = raw_section.lstrip("*")
        is_compressed = raw_section.startswith("*")

        start_time = 0
        if is_compressed:
            total_duration = sum(dur for _, dur, _ in steps)
            for name, duration, color in steps:
                ax.barh(y, duration, left=start_time, height=0.5, color=color, edgecolor='black')
                start_time += duration
            ax.text(start_time + 1, y, f"{total_duration:.3f}", ha='left', va='center', fontsize=8, color='black')
            yticks.append(y)
            ylabels.append(f"{section} (compressed)")
            y += 1
        else:
            for name, duration, color in steps:
                ax.barh(y, duration, left=start_time, height=0.5, color=color, edgecolor='black')
                ax.text(start_time + duration + 1, y, f"{duration:.3f}", ha='left', va='center', fontsize=8, color='black')
                yticks.append(y)
                ylabels.append(f"{section}: {name}")
                start_time += duration
                y += 1
            y += 1

    ax.set_xlabel("Time (s)")
    ax.set_yticks(yticks)
    ax.set_yticklabels(ylabels, fontsize=8)
    ax.invert_yaxis()
    ax.set_title("Gantt Timeline of Benchmark Steps")

    handles = [mpatches.Patch(color=color, label=label) for color, label in color_labels.items()]
    ax.legend(handles=handles, loc='upper right', bbox_to_anchor=(1.15, 1.05))

    plt.tight_layout()
    plt.savefig("gantt_timeline.png", dpi=300)
    plt.show()

if __name__ == "__main__":
    timeline_file = "timeline_data.txt"
    sect, clabel = parse_timeline_file(timeline_file)
    plot_gantt_chart_txt(sect, clabel)

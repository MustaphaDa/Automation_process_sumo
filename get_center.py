import xml.etree.ElementTree as ET

def find_average_center(input_file):
    tree = ET.parse(input_file)
    root = tree.getroot()

    x_sum = 0
    y_sum = 0
    count = 0

    for edge in root.findall('edge'):
        if 'shape' in edge.attrib:
            shape = edge.attrib['shape'].split()
            coords = [tuple(map(float, coord.split(','))) for coord in shape]
            x, y = coords[0]
            x_sum += x
            y_sum += y
            count += 1

    avg_x = x_sum / count
    avg_y = y_sum / count

    return avg_x, avg_y

if __name__ == "__main__":
    INPUT_FILE = "Szeged.net.xml"
    center_x, center_y = find_average_center(INPUT_FILE)
    print(f"Suggested center: ({center_x}, {center_y})")



import argparse
import xml.etree.ElementTree as ET
from xml.dom import minidom
import sumolib


def generate_e2_detectors(
    net_file: str,
    output_file: str,
    detector_freq: int = 60,
    end_offset: float = 5.0,
    start_pos: float = 0.0,
    output_xml_target: str = "e2_output.xml"
) -> None:
    """
    Parses a SUMO network file and generates E2 laneAreaDetectors for each lane.
    
    Args:
        net_file: Path to the input .net.xml file.
        output_file: Destination path for detectors.add.xml.
        detector_freq: Aggregation interval in seconds for detector measurements.
        end_offset: Clearance distance in meters from the lane end to avoid junction conflicts.
        start_pos: Position in meters from the beginning of the lane where detector starts.
        output_xml_target: Target filename attribute inside SUMO where detector records data.
    """
    net = sumolib.net.readNet(net_file, withInternal=False)
    
    root = ET.Element("additional")
    detector_count = 0

    # Iterate over all non-internal edges dynamically without hardcoding
    for edge in net.getEdges(withInternal=False):
        edge_id = edge.getID()
        
        # Guard against internal edges (which start with ':')
        if edge_id.startswith(":"):
            continue

        for lane in edge.getLanes():
            lane_id = lane.getID()
            lane_length = lane.getLength()

            # Determine usable length respecting safety margins
            if lane_length <= end_offset + start_pos:
                detector_pos = 0.0
                detector_length = max(lane_length - 0.5, 1.0)
            else:
                detector_pos = start_pos
                detector_length = lane_length - detector_pos - end_offset

            detector_id = f"e2_{lane_id}"
            
            detector_elem = ET.SubElement(
                root,
                "laneAreaDetector",
                {
                    "id": detector_id,
                    "lane": lane_id,
                    "pos": f"{detector_pos:.2f}",
                    "length": f"{detector_length:.2f}",
                    "freq": str(detector_freq),
                    "file": output_xml_target,
                    "friendlyPos": "true"
                }
            )
            detector_count += 1

    # Pretty-print XML structure
    raw_xml_string = ET.tostring(root, encoding="utf-8")
    parsed_dom = minidom.parseString(raw_xml_string)
    pretty_xml = parsed_dom.toprettyxml(indent="    ", encoding="utf-8")

    with open(output_file, "wb") as f:
        f.write(pretty_xml)

    print(f"Successfully generated {detector_count} E2 detectors in '{output_file}'.")


def main():
    parser = argparse.ArgumentParser(
        description="Generate E2 (laneAreaDetector) definition file for any SUMO network."
    )
    parser.add_argument(
        "-n", "--net-file",
        required=True,
        help="Path to the SUMO network file (.net.xml)"
    )
    parser.add_argument(
        "-o", "--output-file",
        default="detectors.add.xml",
        help="Path to the output additional file (default: detectors.add.xml)"
    )
    parser.add_argument(
        "--freq",
        type=int,
        default=60,
        help="Aggregation interval for detector output in seconds (default: 60)"
    )
    parser.add_argument(
        "--offset",
        type=float,
        default=5.0,
        help="Offset in meters from the end of each lane (default: 5.0)"
    )

    args = parser.parse_args()
    
    generate_e2_detectors(
        net_file=args.net_file,
        output_file=args.output_file,
        detector_freq=args.freq,
        end_offset=args.offset
    )


if __name__ == "__main__":
    main()
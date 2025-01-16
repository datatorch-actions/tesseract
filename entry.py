from datatorch import get_input, agent, set_output
from datatorch.api.api import ApiClient
from datatorch.api.entity.annotation import Annotation
from datatorch.api.entity.sources.image import Segmentations
from datatorch.api.entity.sources.source import Source

from datatorch.api.scripts.utils.simplify import simplify_points

import requests
from requests.exceptions import HTTPError
import docker
import time
import os
import shapely.ops

from shapely import geometry
from typing import List, Tuple
from docker.models.resource import Model
from urllib.parse import urlparse

Point = Tuple[float, float]

directory = os.path.dirname(os.path.abspath(__file__))

agent_dir = agent.directories().root
points = get_input("points")
image_path = get_input("imagePath")
address = urlparse(get_input("url"))
image = get_input("image")
annotation = get_input("annotation")
annotation_id = None
if annotation:
    annotation_id = annotation.get("id")
label_id = get_input("labelId")
file_id = get_input("fileId")
simplify = get_input("simplify")

# [[10,20],[30, 40],[50,60],[70,80]]
# points: List[Point] = [(10.0, 20.0), (30.0, 40.0), (50.0, 60.0), (70.0, 80.0)]
# image_path = "/home/desktop/.config/datatorch/agent/temp/download-file/20201025_102443 (17th copy).jpg"

CONTAINER_NAME = "datatorch-segformer-action"


def return_container_status(container_name: str) -> str:
    """Get the status of a container by it's name

    :param container_name: the name of the container
    :return: string
    """
    # Connect to Docker using the default socket or the configuration
    # in your environment
    docker_client = docker.from_env()

    try:
        container = docker_client.containers.get(container_name)
    except docker.errors.NotFound as exc:
        print(f"Check container name!\n{exc.explanation}")
        return "EEXIST"
    else:
        container_state = container.attrs["State"]
        return container_state["Status"]


def valid_image_path():
    if not image_path.startswith(agent_dir):
        print(f"Directory must be inside the agent folder ({agent_dir}).")
        exit(1)

    if not os.path.isfile(image_path):
        print(f"Image path must be a file ({image_path}).")
        exit(1)


def start_server(port: int):
    docker_client = docker.from_env()
    try:
        # Check if the container exists
        container = docker_client.containers.get(CONTAINER_NAME)
        if container.status == "running":
            print(f"Container {CONTAINER_NAME} already running on port {port}")
            return
        elif container.status == "exited":
            print(f"Restarting existing container {CONTAINER_NAME}.")
            container.start()
            return
        else:
            print(f"Container {CONTAINER_NAME} exists but is in state: {container.status}. Removing and recreating it.")
            container.remove(force=True)
    except docker.errors.NotFound:
        print(f"No existing container found with name {CONTAINER_NAME}. Creating a new one.")

    # Create and run the container if it does not exist or was removed
    print(f"Creating Segformer container on port {port}.")
    print(
        f"Downloading {image} docker image. This may take a few mins.", flush=True
    )
    container = docker_client.containers.run(
        image,
        detach=True,
        ports={"8000/tcp": port},
        restart_policy={"Name": "always"},
        volumes={agent_dir: {"bind": "/agent", "mode": "rw"}},
        name=CONTAINER_NAME,
    )
    if isinstance(container, Model):
        print(f"Created Segformer Container ({container.short_id}).")


def call_model(path: str, points: List[Point], address: str) -> List[List[Point]]:
    agent_folder = agent.directories().root
    container_path = path.replace(agent_folder, "/agent")

    print(f"Sending request to '{address}' (POST)")
    print(f"Image Path = {path}")
    print(f"Container Path = {container_path}")
    print(f"Points = {points}")

    response = requests.post(
        address, json={"path": container_path, "points": points}
    )
    response.raise_for_status()
    json = response.json()
    return json["polygons"]


def remove_polygons_with_2_points(path_data: List[List[Point]]):
    return list(filter(lambda x: len(x) > 2, path_data))


def combine_segmentations(
    path_data_1: List[List[Point]], path_data_2: List[List[Point]]
) -> List[List[Point]]:
    poly_1 = [geometry.Polygon(points) for points in path_data_1]
    poly_2 = [geometry.Polygon(points) for points in path_data_2]

    multi = shapely.ops.unary_union(poly_1 + poly_2)

    path_data = []
    if isinstance(multi, geometry.Polygon):
        path_data.append(list(multi.exterior.coords[:-1]))

    if isinstance(multi, geometry.MultiPolygon):
        for polygon in multi:
            path_data.append(list(polygon.exterior.coords[:-1]))

    return path_data


def send_request(annotation_id=None):
    attempts = 0

    start_server(address.port or 80)
    time.sleep(30)

    while True:
        try:
            attempts += 1
            print(f"Attempt {attempts}: Request to Segformer Server")
            segments = call_model(image_path, points, address.geturl())
            print(len(segments))
            for seg in segments:
                if simplify == 0:
                    input_seg = seg
                else:
                    input_seg = [
                        simplify_points(
                            polygon, tolerance=simplify, highestQuality=False
                        )
                        for polygon in seg
                    ]

                output_seg = remove_polygons_with_2_points(input_seg)
                set_output("polygons", output_seg)
                print(f"Annotation ID: {annotation_id}")

                if annotation:
                    try:
                        s = Segmentations()
                        s.annotation_id = annotation_id

                        existing_segmentation = next(
                            x
                            for x in annotation.get("sources")
                            if x.get("type") == "PaperSegmentations"
                        )
                        print(
                            f"Updating segmentation for annotation {annotation_id}",
                            flush=True,
                        )
                        s.id = existing_segmentation.get("id")
                        s.path_data = combine_segmentations(
                            output_seg,
                            remove_polygons_with_2_points(
                                existing_segmentation.get("pathData")
                            ),
                        )
                        s.save(ApiClient())
                    except StopIteration:
                        if annotation_id is not None:
                           print(
                               f"Creating segmentation source for annotation {annotation_id}"
                           )
                           s.path_data = output_seg  # type: ignore
                           s.create(ApiClient())
                else:
                    new_annotation = Annotation()
                    new_annotation.label_id = label_id
                    new_annotation.file_id = file_id
                    new_annotation.create(ApiClient())
                    annotation_id = new_annotation.id
                    print(f"Creating segmentation for annotation {annotation_id}")

                    s = Segmentations()
                    s.annotation_id = annotation_id
                    s.path_data = output_seg
                    s.create(ApiClient())
                    print("Segmentation created")

                    # exit(0)

            exit(0)
        except HTTPError as http_err:
            print(http_err)
            print(f"Attempt {attempts}: Could not connect to model.")
            if attempts > 5:
                break
            start_server(address.port or 80)
            time.sleep(20)
        except Exception as ex:
            print("Exception", ex, flush=True)
            break

    print("Could not send request.")
    exit(1)


if __name__ == "__main__":
    valid_image_path()
    send_request(annotation_id=annotation_id)

import cv2
import numpy as np
import math

MM_PER_PIXEL = 0.00119
HEIGHT = 0.1



def count(img, dilution_ratio):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    gray = cv2.GaussianBlur(gray, (5,5), 0)

    otsu_value, _ = cv2.threshold(
        gray,
        0,
        255,
        cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )

    new_value = otsu_value + 33
    _, binary = cv2.threshold(
        gray, new_value, 255,
        cv2.THRESH_BINARY
    )

    kernel = np.ones((3, 3), np.uint8)

    binary = cv2.morphologyEx(
        binary,
        cv2.MORPH_OPEN,
        kernel
    )

    dist = cv2.distanceTransform(binary, cv2.DIST_L2, 5)
    dist_norm = cv2.normalize(dist, None, 0, 1.0, cv2.NORM_MINMAX)
    dist_binary = (dist_norm > 0.095).astype(np.uint8) * 255 

    num_labels, blob_labels, stats, _ = cv2.connectedComponentsWithStats(dist_binary, 8)
    line_test = np.zeros_like(dist_binary)
    fill_threshold = 0.85
    line_threshold = 1.24
    area_threshold = 80
    area_upper_thresh = 450
    for label in range(1, num_labels):
        width = stats[label, cv2.CC_STAT_WIDTH]
        height = stats[label, cv2.CC_STAT_HEIGHT]
        area = stats[label, cv2.CC_STAT_AREA]
        x = stats[label, cv2.CC_STAT_LEFT]
        y = stats[label, cv2.CC_STAT_TOP]

        if area < area_threshold: continue

        Y, X = np.ogrid[:height, :width]
        circle_mask = ((X - (width/2))**2 + (Y - (height/2))**2 <= (min(width, height) / 2)**2)
        component = (blob_labels[y:y+height, x:x+width] == label)
        circle_pixels = np.sum(circle_mask)
        white_pixels = np.sum(component & circle_mask)
        
        fill_ratio = white_pixels / circle_pixels
        line_ratio = max(width,height) / min(width,height)
        if line_ratio >= line_threshold or fill_ratio <= fill_threshold or area >= area_upper_thresh:
            line_test[blob_labels == label] = 255

    sure_fg = np.zeros_like(binary)
    sure_fg = (dist_norm > 0.1).astype(np.uint8) * 255
    num_labels, markers = cv2.connectedComponents(sure_fg)

    markers += 1

    sure_bg = cv2.dilate(binary, kernel, iterations=3)

    unknown = cv2.subtract(sure_bg, sure_fg)
    markers[unknown == 255] = 0

    markers = cv2.watershed(img, markers)

    labels = np.unique(markers)
    single_cell_count = 0
    single_cell_pixels = 0

    for label in labels:
        if label <= 1: continue

        cell_mask = (markers == label)

        overlaps_blob = np.any(line_test[cell_mask] == 255)

        if overlaps_blob: continue

        single_cell_count += 1
        single_cell_pixels += np.sum(cell_mask)

    single_cell_area = single_cell_pixels / single_cell_count

    contours, _ = cv2.findContours(line_test, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    multi_cell_count = 0

    for contour in contours:
        blob_mask = np.zeros_like(line_test)

        cv2.drawContours(blob_mask, [contour], -1, 255, -1)

        ########### Did *1.2 to blob area to compensate for the fact that this is comming from dist_transform instead of the single cell area is coming from the watershed!!!!


        blob_area = np.sum(blob_mask == 255) * 1.2
        estimated_cells_in_blob = math.ceil(blob_area / single_cell_area)

        multi_cell_count += estimated_cells_in_blob

    estimated_count = single_cell_count + multi_cell_count

    result = img.copy()

    result[markers == -1] = [0, 255, 0]

    cv2.drawContours(result, contours, -1, (0, 0, 255), 2)

    img_height, img_width = gray.shape
    
    mmheight = img_height * MM_PER_PIXEL
    mmwidth = img_width * MM_PER_PIXEL

    img_area = mmheight * mmwidth
    countpermm2=estimated_count/img_area

    concentration = countpermm2*1e4*dilution_ratio
    
    print("Cells: ", estimated_count)
    print("Concentration: ", concentration)

    return estimated_count, concentration, result
import cv2
import numpy as np

MM_PER_PIXEL = 0.00625
HEIGHT = 0.1

def count(img):
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
    fill_threshold = 0.86
    line_threshold = 1.22
    area_threshold = 200
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
        if line_ratio >= line_threshold or fill_ratio <= fill_threshold:
            line_test[blob_labels == label] = 255

    """
    skeleton = skeletonize(line_test > 0)
    skeleton_display = (skeleton * 255).astype(np.uint8)
    cv2.imshow("Skeleton", skeleton_display)
    cv2.waitKey(0)
    """

    sure_fg = np.zeros_like(binary)
    sure_fg = (dist_norm > 0.1).astype(np.uint8) * 255
    num_labels, markers = cv2.connectedComponents(sure_fg)

    markers += 1

    sure_bg = cv2.dilate(binary, kernel, iterations=3)

    unknown = cv2.subtract(sure_bg, sure_fg)
    markers[unknown == 255] = 0

    markers = cv2.watershed(img, markers)

    result = img.copy()
    result[markers == -1] = [0,255,0]
    contours, _ = cv2.findContours(
        line_test,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE
    )

    cv2.drawContours(result, contours, -1, (0,0,255), 2)

    labels = np.unique(markers)

    cell_count = 0

    for label in labels:

        if label <= 1:
            continue

        cell_count += 1

    multie_blob_count = len(contours)

    estimated_count = round(cell_count + multie_blob_count * (2.1-1))


    img_height, img_width = gray.shape

    umheight = img_height * MM_PER_PIXEL
    umwidth = img_width * MM_PER_PIXEL

    img_area = umheight * umwidth * HEIGHT

    concentration = (estimated_count * 2 * 10**4)/img_area
    print("Cells: ", estimated_count)
    print("Concentration: ", concentration)

    return estimated_count, concentration, result

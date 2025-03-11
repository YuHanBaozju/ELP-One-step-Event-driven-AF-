import glob
import time

import matplotlib.pyplot as plt
import numpy as np
import cv2
import os
from PIL import Image
from utils.filter import update_filter_laplacian_product

# from motion_compensate.motion_compare_edge_log_cut_trail import motion_compare

# 初始化全局变量
roi_start = None
roi_end = None
drawing = False
img = None
img_copy = None
ROI = None  # 用于存储ROI区域

# 是否进行运动补偿

warp_enable = False

# 鼠标回调函数，用于处理鼠标事件
# 鼠标回调函数，用于处理鼠标事件
def mouse_callback(event, x, y, flags, param):
    global roi_start, roi_end, drawing, img_copy, ROI

    # 当左键按下时，开始绘制 ROI
    if event == cv2.EVENT_LBUTTONDOWN:
        drawing = True
        roi_start = (x, y)
        roi_end = (x, y)  # 初始化结束坐标与开始坐标相同

    # 当鼠标移动时，更新 ROI 结束位置
    elif event == cv2.EVENT_MOUSEMOVE:
        if drawing:
            roi_end = (x, y)
            img_copy = img.copy()  # 在临时图像上绘制矩形框
            cv2.rectangle(img_copy, roi_start, roi_end, (0, 255, 0), 2)
            cv2.imshow("Image", img_copy)

    # 当左键释放时，完成 ROI 的绘制并关闭窗口
    elif event == cv2.EVENT_LBUTTONUP:
        drawing = False
        roi_end = (x, y)
        cv2.rectangle(img_copy, roi_start, roi_end, (0, 255, 0), 2)
        cv2.imshow("Image", img_copy)

        # 确定ROI的四个边界值
        x1, y1 = min(roi_start[0], roi_end[0]), min(roi_start[1], roi_end[1])
        x2, y2 = max(roi_start[0], roi_end[0]), max(roi_start[1], roi_end[1])
        ROI = ( y1, y2,x1, x2)  # 存储 ROI 的四个边界值

        # 输出最终选择的 ROI 区域
        print(f"ROI selected: {ROI}")

        # 关闭窗口
        cv2.destroyAllWindows()

def render(image, x, y, p):
    """
    make event image
    """
    height, width = image.shape[:2]
    x = np.clip(x, 0, width - 1)
    y = np.clip(y, 0, height - 1)
    image[y[p == 1.], x[p == 1.], 2] = 255
    image[y[p == 0.], x[p == 0.], 0] = 255

    return image



def event_acc(events,shape):
    p_events = np.zeros(shape=(shape[0],shape[1]),dtype='uint8')
    n_events = np.zeros(shape=(shape[0],shape[1]),dtype='uint8')
    for event in events:
        if event[3] == 1:
            p_events[event[2],event[1]] += 1
        else:
            n_events[event[2],event[1]] += 1
    return p_events,n_events



def elp_real_davis(root_folder,vis=False,ablation_on='filter'):
    event = np.load(root_folder + '/event.npy')

    import re

    # 打开并读取文件内容
    with open(root_folder + '/info.txt', 'r') as file:
        data = file.read()

    start_time_pattern = r'start_timestamp\s*=\s*(\d+)'
    start_time_match = re.search(start_time_pattern, data)
    if start_time_match:
        start_time = int(start_time_match.group(1))
        # print(f"start_time: {start_time}")

    end_time_pattern = r'end_timestamp\s*=\s*(\d+)'
    end_time_match = re.search(end_time_pattern, data)
    if end_time_match:
        end_time = int(end_time_match.group(1))
        # print(f"end_time: {end_time}")

    gt_time_pattern = r'gt_timestamp\s*=\s*(\d+)'
    gt_time_match = re.search(gt_time_pattern, data)
    if gt_time_match:
        gt_timestamp = int(gt_time_match.group(1))
        # print(f"gt_timestamp: {gt_timestamp}")

    delta_t_pattern = r'delta_t\s*=\s*([\d.]+)'
    delta_t_match = re.search(delta_t_pattern, data)
    if delta_t_match:
        delta_t = float(delta_t_match.group(1))
        # print(f"delta_t: {delta_t}")
    else:
        delta_t = 1e3
        # print(f"delta_t: {delta_t}")

    # 使用正则表达式查找ROI selected的值
    roi_pattern = r'ROI selected:\s*\(\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+)\s*\)'
    roi_match = re.search(roi_pattern, data)

    event = event[(event[:, 0] >= start_time) & (event[:, 0] <= end_time)]

    frame_folder = root_folder + '/frames'

    jpg_files = glob.glob(os.path.join(frame_folder, '*.jpg'))

    if ablation_on == 'laplacian':
        start_time += 25e3

    selected_files = [file for file in jpg_files if
                      start_time <= int(os.path.splitext(os.path.basename(file))[0]) <= end_time]

    timestamp_list = [int(os.path.splitext(os.path.basename(file))[0]) for file in selected_files]

    laplacian_product = []

    filter_laplacian_product = []
    t_list = []

    find_focus = False

    img_path = selected_files[0]
    img = cv2.imread(img_path)

    if img is None:
        print("Failed to load the image.")
    else:
        if roi_match:
            ROI = tuple(map(int, roi_match.groups()))
            # print(f"ROI selected: {ROI}")
        else:

            img_copy = img.copy()  # 创建一个副本用于交互
            cv2.namedWindow("EvTemMap")
            cv2.setMouseCallback("EvTemMap", mouse_callback)

            # 显示图像，等待用户选择 ROI
            while True:
                cv2.imshow("EvTemMap", img_copy)
                key = cv2.waitKey(1) & 0xFF
                if key == 27:  # 按下 'ESC' 退出程序（备选项）
                    break

    runtime = 0
    for i, file in enumerate(selected_files):

        if i == len(selected_files) - 1 or find_focus:
            break

        event_all = event[(event[:, 0] >= timestamp_list[i]) & (event[:, 0] <= timestamp_list[i + 1])]

        # if i%5 == 0:
        img = cv2.imread(file, cv2.IMREAD_UNCHANGED)
        img = cv2.medianBlur(img, 3)
        # img_roi = img[roi[0]:roi[1], roi[2]:roi[3]]
        if ablation_on == 'laplacian':
            laplacian = np.ones(img.shape, dtype='float32')
        else:
            laplacian = cv2.Laplacian(img, cv2.CV_32F)


        laplacian_mask = np.zeros_like(laplacian)
        laplacian_mask[ROI[0]:ROI[1], ROI[2]:ROI[3]] = laplacian[ROI[0]:ROI[1], ROI[2]:ROI[3]]
        laplacian = laplacian_mask
        laplacian_warp = laplacian.copy()

        img_show = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        # img_show = cv2.rectangle(img_show, (ROI[2], ROI[0]), (ROI[3], ROI[1]), (0, 255, 0), 2)

        event_all = event_all[
            (event_all[:, 2] >= ROI[0]) & (event_all[:, 2] <= ROI[1]) & (event_all[:, 1] >= ROI[2]) & (
                        event_all[:, 1] <= ROI[3])]

        t = timestamp_list[i]

        while t < timestamp_list[i + 1]:
            if find_focus:
                break
            event_sample = event_all[(event_all[:, 0] >= t) & (event_all[:, 0] <= t + delta_t)]

            if len(event_sample) == 0:
                t += delta_t
                continue
            runtime_start = time.time()
            p_events, n_events = event_acc(event_sample, laplacian.shape)

            if warp_enable:
                warp_matrix = motion_compare(img, event_sample)

                img = cv2.warpAffine(img, warp_matrix, (img.shape[1], img.shape[0]))

                img_show = cv2.warpAffine(img_show, warp_matrix, (img.shape[1], img.shape[0]))
                laplacian_warp = cv2.warpAffine(laplacian_warp, warp_matrix, (img.shape[1], img.shape[0]))
                laplacian_product_index = (-np.sum(laplacian_warp * p_events) + np.sum(laplacian_warp * n_events)) / \
                                          event_sample.shape[0]
            else:
                laplacian_product_index = (-np.sum(laplacian_warp * p_events) + np.sum(laplacian_warp * n_events)) / \
                                          event_sample.shape[0]

            laplacian_product.append(laplacian_product_index)
            t_list.append(t - start_time)

            threshold = 5e4  # 设置一个阈值来检测突变
            alpha = 0.4  # 平滑系数
            filter_size = 10

            if ablation_on == 'filter':
                ## for ablating the filter
                filter_laplacian_product = laplacian_product
            else:
                filter_laplacian_product = update_filter_laplacian_product(laplacian_product, filter_laplacian_product,
                                                                       threshold,
                                                                       alpha, window_size=filter_size)

            runtime += time.time() - runtime_start

            event_frame = np.zeros((img.shape[0], img.shape[1], 3), dtype='uint8')
            event_frame = render(event_frame, event_sample[:, 1], event_sample[:, 2], event_sample[:, 3])

            t += delta_t
            add = cv2.addWeighted(img_show, 1, event_frame, 1, 0)

            if ablation_on == 'laplacian':
                mutation_detect_amp = 0.6
                mutation_detect_min = -0.5
            else:
                mutation_detect_amp = 8
                mutation_detect_min = -5

            if max(filter_laplacian_product) - min(filter_laplacian_product) > mutation_detect_amp and min(filter_laplacian_product) < mutation_detect_min:
                # 将列表转换为 NumPy 数组
                arr = np.array(filter_laplacian_product)

                # 找到从正数跳到负数的位置，判断前一个元素为正，当前元素为负
                transitions = np.where((arr[:-1] > 0) & (arr[1:] < 0))[0] + 1

                # transitions = (filter_laplacian_product.index(min(filter_laplacian_product[-10:])) + filter_laplacian_product.index(max(filter_laplacian_product[-10:])))//2

                focus_timestamp = t_list[transitions[-1]] - delta_t
                if vis:
                    add = cv2.putText(add, f'focus_timestamp: {focus_timestamp}', (0, 30), cv2.FONT_HERSHEY_DUPLEX, 0.5,
                                      (0, 255, 0))
                    cv2.imshow('show', add)
                    if find_focus:
                        cv2.waitKey(1)
                    else:
                        cv2.waitKey(0)
                find_focus = True

            if vis:
                cv2.imshow('show', add)
                cv2.waitKey(1)

    cv2.destroyAllWindows()
    if vis:
        print(f'runtime: {runtime * 1e3}')
        print(f'runtime/step: {runtime / len(t_list) * 1e3}')
        plt.plot(t_list, laplacian_product)
        plt.plot(t_list, filter_laplacian_product, color='red')
        if find_focus:
            plt.axvline(x=focus_timestamp, color='green', linestyle='--')
        plt.axvline(x=gt_timestamp - start_time, color='black', linestyle='-')
        plt.show()

    print(f'error: {focus_timestamp - gt_timestamp + start_time}')

    if vis:
        # 将时间列表转换为 NumPy 数组
        time_array = np.array(timestamp_list)

        # 计算每个时间与给定时间戳的差值的绝对值
        differences = np.abs(time_array - focus_timestamp - start_time)

        # 找到最小差值的索引
        closest_index = np.argmin(differences)

        focus_img = cv2.imread(selected_files[closest_index])
        print(selected_files[closest_index])

        cv2.imshow(selected_files[closest_index], focus_img)
        cv2.waitKey(0)


# root_folder = r'E:\Event_camera\DVS_AF_est\dataset\DAVIS346\focusboard\bright_static'
# elp_real_davis(root_folder,vis=True)
